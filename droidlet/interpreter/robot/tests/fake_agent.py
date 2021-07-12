"""
Copyright (c) Facebook, Inc. and its affiliates.
"""

import numpy as np
import re
import logging
import math

from droidlet.base_util import Look, to_player_struct
from droidlet.interpreter.robot import dance
from droidlet.memory.memory_nodes import PlayerNode
from agents.loco_mc_agent import LocoMCAgent
from droidlet.perception.semantic_parsing.nsp_querier import NSPQuerier
from droidlet.dialog.dialogue_manager import DialogueManager
from droidlet.dialog.map_to_dialogue_object import DialogueObjectMapper
from droidlet.memory.robot.loco_memory import LocoAgentMemory
from droidlet.memory.robot.loco_memory_nodes import DetectedObjectNode
from droidlet.lowlevel.robot_mover_utils import (
    get_camera_angles,
    angle_diff,
    CAMERA_HEIGHT,
    MAX_PAN_RAD,
)

# FXIME!!! everything here should be essentially self-contained
from agents.locobot.self_perception import SelfPerception
import droidlet.lowlevel.rotation as rotation
from droidlet.perception.robot.tests.utils import get_fake_detection

# these should go in utils
from droidlet.shared_data_struct.robot_shared_utils import Pos

# marker creation should be somewhwere else....
from droidlet.interpreter.robot import LocoGetMemoryHandler, PutMemoryHandler, LocoInterpreter


MV_SPEED = 0.2
ROT_SPEED = 1.0  # rad/tick
HEAD_SPEED = 1.0  # rad/tick


class Opt:
    pass


# FIXME use Detection class, etc.  mock less
class FakeDetectorPerception:
    def __init__(self, agent, perceive_freq=10):
        self.agent = agent

    def perceive(self, force=False):
        pass

    def add_detected_object(self, xyz, class_label=None, properties=[], colour=None):
        d = get_fake_detection(class_label, properties, xyz)
        return DetectedObjectNode.create(self.agent.memory, d)


class FakeMoverCommand:
    NAME = "NULL"

    def __init__(self, mover, agent):
        self.mover = mover
        self.agent = agent
        self.count = 0

    def action(self, *args):
        pass

    def finish(self):
        self.finished = True
        self.mover.current_action = None

    def get_step_data(self):
        return [self.count]

    def step(self):
        self.count += 1
        if hasattr(self.agent, "recorder"):
            self.agent.recorder.record_action(
                {"name": self.NAME, "step_data": self.get_step_data()}
            )

    def __call__(self, *args):
        if hasattr(self.agent, "recorder"):
            self.agent.recorder.record_action({"name": self.NAME, "args": list(args)})
        return self.action(*args)


def abs_min(x, y):
    s = np.sign(y)
    py = y * s
    px = x * s
    return s * np.minimum(py, px)


class MoveAbsolute(FakeMoverCommand):
    NAME = "move_absolute"

    def action(self, xyt_positions):
        self.xyt_positions = xyt_positions
        self.position_index = 0
        self.agent.mover.current_action = self
        self.finished = False
        return self.finished

    def get_step_data(self):
        return [self.count] + self.agent.pos.tolist() + [self.agent.base_yaw]

    def step(self):
        super().step()
        xyt = np.array(self.xyt_positions[self.position_index])
        p = np.array([self.agent.pos[0], self.agent.pos[1], self.agent.base_yaw])
        res = xyt - p
        if np.linalg.norm(res) < 0.01:
            self.position_index += 1
            if self.position_index >= len(self.xyt_positions):
                self.finish()
                return self.finished
            res = np.array(self.xyt_positions[self.position_index]) - p

        # FIXME! this is a bug
        mv = np.array(
            [
                np.sign(res[0]) * self.agent.mv_speed,
                np.sign(res[1]) * self.agent.mv_speed,
                np.sign(res[2]) * self.agent.rot_speed,
            ]
        )
        change = abs_min(res, mv)
        self.agent.pos += change[:2]
        self.agent.base_yaw += change[2]
        return self.finished


class Turn(FakeMoverCommand):
    NAME = "turn"

    def action(self, yaw):
        self.yaw = yaw
        self.agent.mover.current_action = self
        self.finished = False
        return self.finished

    def step(self):
        super().step()
        turn_rad = self.yaw * math.pi / 180
        self.agent.base_yaw += turn_rad
        self.finish()
        return self.finished


class GrabNearbyObject(FakeMoverCommand):
    NAME = "grab_nearby_object"

    def action(self):
        self.finished = False
        self.agent.mover.current_action = self
        return self.finished

    def get_step_data(self):
        return [self.count] + self.agent.pos.tolist() + [self.agent.base_yaw]

    def step(self):
        super().step()
        if self.mover.gripper_state == "occupied":
            # TODO some sort of failure notice
            self.finished = True
            return self.finished
        # TODO pick the one most in view instead of closest:
        objects = self.agent.world.objects
        if len(objects) == 0:
            # TODO some sort of failure notice
            self.finished = True
            return self.finished
        ax, az = (self.agent.pos[0], self.agent.pos[1])
        closest_object = sorted(
            objects, key=lambda o: (o["pos"][0] - ax) ** 2 + (o["pos"][2] - az) ** 2
        )[0]
        self.gripper_state = "occupied"
        self.agent.world.attach_object_to_agent(closest_object, self.agent)
        self.finished = True
        return self.finished


class Drop(FakeMoverCommand):
    NAME = "drop"

    def action(self):
        self.finished = False
        self.agent.mover.current_action = self
        return self.finished

    def get_step_data(self):
        return [self.count] + self.agent.pos.tolist() + [self.agent.base_yaw]

    def step(self):
        super().step()
        if self.gripper_state == "occupied":
            # drop everything rn
            for obj in self.agent.world.objects:
                self.agent.world.detach_object_from_agent(obj, self.agent)
            self.gripper_state = "open"
            self.finished = True
            return self.finished
        else:
            # TODO some sort of failure notice
            self.finished = True
            return self.finished


class SendChat(FakeMoverCommand):
    NAME = "send_chat"

    def action(self, chat):
        logging.info("FakeAgent.send_chat: {}".format(chat))
        self.finished = True
        self.agent._outgoing_chats.append(chat)
        return self.finished


# TODO? have a base class, use the same for real and fake locobot mover,
# but use different backend
class LookAt(FakeMoverCommand):
    NAME = "look_at"

    def action(self, marker_pos, yaw_deg, pitch_deg):
        self.agent.mover.current_action = self
        old_pan = self.mover.get_pan()
        old_tilt = self.mover.get_tilt()
        pan_rad, tilt_rad = 0.0, 0.0
        pos = self.mover.get_base_pos()  # (x, z, yaw)

        if yaw_deg:  # if relative yaw angle
            pan_rad = old_pan - float(yaw_deg) * np.pi / 180
        if pitch_deg:  # if relative pitch angle
            tilt_rad = old_tilt - float(pitch_deg) * np.pi / 180
        if marker_pos is not None:
            # 1.0 is approx camera height, FIXME
            logging.info(f"looking at x,y,z: {marker_pos}")
            pan_rad, tilt_rad = get_camera_angles([pos[0], CAMERA_HEIGHT, pos[1]], marker_pos)
            logging.debug(f"Returned new pan and tilt angles (radians): ({pan_rad}, {tilt_rad})")

        head_res = angle_diff(pos[2], pan_rad)
        if np.abs(head_res) > MAX_PAN_RAD:
            dyaw = np.sign(head_res) * (np.abs(head_res) - MAX_PAN_RAD)
            self.target_yaw = pos[2] + dyaw
            pan_rad = np.sign(head_res) * MAX_PAN_RAD
        else:
            self.target_yaw = pos[2]
            pan_rad = head_res
        logging.info(f"Camera pan and tilt angles (radians): ({pan_rad}, {tilt_rad})")
        self.target_pan_tilt = np.array([pan_rad, tilt_rad])
        self.finished = False
        return self.finished

    def get_step_data(self):
        return [self.count, self.agent.base_yaw, self.agent.pan, self.agent.tilt]

    def step(self):
        super().step()
        print(self.count)
        dyaw = self.target_yaw - self.agent.base_yaw
        if np.abs(dyaw) > 0.001:
            mv = abs_min(np.sign(dyaw) * self.agent.rot_speed, dyaw)
            self.agent.base_yaw += mv
            return self.finished
        p = np.array([self.agent.pan, self.agent.pitch])
        res = self.target_pan_tilt - p
        print(res)
        if np.linalg.norm(res) < 0.01:
            self.finish()
            return self.finished
        mv = np.sign(res) * self.agent.head_speed
        change = abs_min(res, mv)
        self.agent.pan += change[0]
        self.agent.pitch += change[1]
        return self.finished


"""
    def point_at(self, target_pos):
        yaw_rad, pitch_rad = get_camera_angles(target_pos)
        self.bot.set_joint_positions([yaw_rad, 0.0, pitch_rad, 0.0, 0.0], plan=False)

        # make a wave-like pointing
        for _ in range(3):
            self.bot.set_joint_positions([yaw_rad, 0.0, pitch_rad, 0.0, 0.0], plan=False)
            ###FIXME!!!!
            while not self.bot.command_finished():
                time.sleep(0.5)
            self.bot.set_joint_positions([yaw_rad, 0.0, pitch_rad, -0.2, 0.0], plan=False)
            while not self.bot.command_finished():
                time.sleep(0.5)

        # reset the joint positions
        self.bot.set_joint_positions([0.0, -math.pi / 4.0, math.pi / 2.0, 0.0, 0.0], plan=False)
"""


class FakeLocobot:
    def __init__(self):
        self._done = True

    def set_joint_positions(self, target_joint, plan=False):
        pass

    def command_finished(self):
        return self._done


class FakeMover:
    def __init__(self, agent):
        self.agent = agent
        self.bot = FakeLocobot()
        self.current_action = None
        self.move_absolute = MoveAbsolute(self, agent)
        self.send_chat = SendChat(self, agent)
        self.look_at = LookAt(self, agent)
        self.grab_nearby_object = GrabNearbyObject(self, agent)
        self.drop = Drop(self, agent)
        self.turn = Turn(self, agent)
        self.gripper_state = "open"  # open, closed, occupied

    #        self.set_joint_positions = SetJointPositions(agent)
    #        self.set_pan = SetPan(agent)
    #        self.set_pan_tilt = SetPanTilt(agent)
    #        self.set_tilt = SetTilt(agent)

    #        self.set_joint_velocities = SetJointVelocities(agent)
    #        self.set_ee_pose = SetEEPose(agent)
    #        self.move_ee_xyz = MoveEEXYZ(agent)
    #        self.open_gripper = OpenGripper(agent)
    #        self.close_gripper = CloseGripper(agent)

    def bot_step(self):
        if not self.current_action:
            return True
        else:
            return self.current_action.step()

    def is_object_in_gripper(self):
        return self.gripper_state == "occupied"

    def set_gripper_state(self, state):
        assert state in ["occupied", "open", "closed"]
        self.gripper_state = state

    def get_base_pos(self):
        return [self.agent.pos[0], self.agent.pos[1], self.agent.base_yaw]

    def get_base_pos_in_canonical_coords(self):
        return [self.agent.pos[0], self.agent.pos[1], self.agent.base_yaw]

    def get_tilt(self):
        return self.agent.pitch

    def get_pan(self):
        return self.agent.pan

    def reset(self):
        pass

    def get_base_state(self):
        pass

    def get_gripper_position(self):
        pass

    def get_end_eff_pose(self):
        pass

    def get_joint_positions(self):
        pass

    def get_joint_velocities(self):
        pass

    def get_camera_state(self):
        pass


class FakeAgent(LocoMCAgent):
    coordinate_transforms = rotation

    def __init__(
        self, world, opts=None, mv_speed=MV_SPEED, rot_speed=ROT_SPEED, head_speed=HEAD_SPEED
    ):
        self.world = world
        self.world.agent = self
        self.chat_count = 0
        if not opts:
            opts = Opt()
            opts.nsp_models_dir = ""
            opts.nsp_data_dir = ""
            opts.model_base_path = ""
            opts.ground_truth_data_dir = ""
            opts.no_ground_truth = True
            opts.log_timeline = False
            opts.enable_timeline = False
        super(FakeAgent, self).__init__(opts)
        self.no_default_behavior = True
        self.last_task_memid = None
        pos = (0.0, 0.0)

        if hasattr(self.world, "agent_data"):
            pos = self.world.agent_data["pos"]
        self.pos = np.array(pos)
        self.base_yaw = 0.0
        self.pan = 0.0
        self.pitch = 0.0
        self.mv_speed = mv_speed
        self.rot_speed = rot_speed
        self.head_speed = head_speed
        self.logical_form = None
        self._outgoing_chats = []
        self.inventory = []

    def init_perception(self):
        self.chat_parser = NSPQuerier(self.opts)
        self.perception_modules = {}
        self.perception_modules["self"] = SelfPerception(self, perceive_freq=1)
        self.perception_modules["vision"] = FakeDetectorPerception(self)

    def init_physical_interfaces(self):
        self.mover = FakeMover(self)
        self.send_chat = self.mover.send_chat

    def init_memory(self):
        self.memory = LocoAgentMemory(coordinate_transforms=self.coordinate_transforms)
        dance.add_default_dances(self.memory)

    def init_controller(self):
        dialogue_object_classes = {}
        dialogue_object_classes["interpreter"] = LocoInterpreter
        dialogue_object_classes["get_memory"] = LocoGetMemoryHandler
        dialogue_object_classes["put_memory"] = PutMemoryHandler
        self.dialogue_manager = DialogueManager(
            memory=self.memory,
            dialogue_object_classes=dialogue_object_classes,
            dialogue_object_mapper=DialogueObjectMapper,
            opts=self.opts,
        )

    def set_logical_form(self, lf, chatstr, speaker):
        self.logical_form = {"logical_form": lf, "chatstr": chatstr, "speaker": speaker}

    def step(self):
        if hasattr(self.world, "step"):
            self.world.step()
        if hasattr(self, "recorder"):
            self.recorder.record_world()
        super().step()

    #### use the LocobotAgent.controller_step()
    def controller_step(self):
        if self.logical_form is None:
            super().controller_step()
        else:  # logical form given directly:
            # clear the chat buffer
            self.get_incoming_chats()
            # use the logical form as given...
            d = self.logical_form["logical_form"]
            chatstr = self.logical_form["chatstr"]
            speaker_name = self.logical_form["speaker"]
            chat_memid = self.memory.add_chat(self.memory.get_player_by_name(speaker_name).memid, chatstr)
            logical_form_memid = self.memory.add_logical_form(d)
            self.memory.add_triple(subj=chat_memid, pred_text="has_logical_form", obj=logical_form_memid)
            self.memory.tag(subj_memid=chat_memid, tag_text="unprocessed")

            # controller
            logical_form = self.dialogue_manager.dialogue_object_mapper.postprocess_logical_form(
                speaker=speaker_name, chat=chatstr, logical_form=d
            )
            obj = self.dialogue_manager.dialogue_object_mapper.handle_logical_form(
                speaker=speaker_name, logical_form=logical_form, chat=chatstr
            )
            self.memory.untag(subj_memid=chat_memid, tag_text="unprocessed")
            if obj is not None:
                self.dialogue_manager.dialogue_stack.append(obj)
            self.logical_form = None

    def setup_test(self):
        self.task_steps_count = 0

    def clear_outgoing_chats(self):
        self._outgoing_chats.clear()

    def get_last_outgoing_chat(self):
        try:
            return self._outgoing_chats[-1]
        except IndexError:
            return None

    def get_info(self):
        info = {}
        # todo self.pos ---> self.camera_pos, self.base_pos
        info["pos"] = self.pos
        info["pitch"] = self.pitch
        info["yaw"] = self.yaw
        info["pan"] = self.pan
        info["base_yaw"] = self.base_yaw
        info["name"] = self.name
        return info

    ########################
    ##  FAKE .PY METHODS  ##
    ########################

    def point_at(*args):
        pass

    # TODO mirror this logic in real locobot
    def get_incoming_chats(self):
        c = self.chat_count
        for raw_chatstr in self.world.chat_log[c:]:
            match = re.search("^<([^>]+)> (.*)", raw_chatstr)
            speaker_name = match.group(1)
            if not self.memory.get_player_by_name(speaker_name):
                # FIXME! name used as eid
                PlayerNode.create(
                    self.memory,
                    to_player_struct((None, None, None), None, None, speaker_name, speaker_name),
                )
        self.chat_count = len(self.world.chat_log)
        return self.world.chat_log[c:].copy()

    def get_player_struct_by_name(self, speaker_name):
        p = self.memory.get_player_by_name(speaker_name)
        if p:
            return p.get_struct()
        else:
            return None

    def get_other_players(self):
        return self.world.players.copy()

    def get_vision(self):
        raise NotImplementedError()

    def get_line_of_sight(self):
        raise NotImplementedError()

    def get_look(self):
        return Look(self.pitch, self.base_yaw + self.pan)

    def get_player_line_of_sight(self, player_struct):
        if hasattr(self.world, "get_line_of_sight"):
            pos = (player_struct.pos.x, player_struct.pos.y, player_struct.pos.z)
            pitch = player_struct.look.pitch
            yaw = player_struct.look.yaw
            xsect = self.world.get_line_of_sight(pos, yaw, pitch)
            if xsect is not None:
                return Pos(*xsect)
        else:
            raise NotImplementedError()

    ######################################
    ## World setup
    ######################################

    # TODO put this in the world, decide if things can move through it, etc.
    def add_object(self, xyz, tags=[], colour=None):
        self.world.add_object(list(xyz), tags=tags, colour=colour)
        # TODO do this better when less mocked
        self.perception_modules["vision"].add_detected_object(xyz, properties=tags, colour=colour)
