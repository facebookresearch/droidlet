"""
Copyright (c) Facebook, Inc. and its affiliates.
"""

import os
import subprocess
import time
import signal
import random
import logging
import faulthandler
from multiprocessing import set_start_method

from droidlet import dashboard

if __name__ == "__main__":
    # this line has to go before any imports that contain @sio.on functions
    # or else, those @sio.on calls become no-ops
    dashboard.start()

from droidlet.dialog.dialogue_manager import DialogueManager
from droidlet.dialog.droidlet_nsp_model_wrapper import DroidletNSPModelWrapper
from droidlet.base_util import to_player_struct, Pos, Look, Player
from droidlet.memory.memory_nodes import PlayerNode
from agents.loco_mc_agent import LocoMCAgent
from agents.argument_parser import ArgumentParser
from droidlet.memory.robot.loco_memory import LocoAgentMemory
from droidlet.perception.robot import Perception, SelfPerception
from droidlet.interpreter.robot import (
    dance, 
    default_behaviors,
    LocoGetMemoryHandler, 
    PutMemoryHandler, 
    LocoInterpreter,
)
from droidlet.dialog.robot import LocoBotCapabilities
import droidlet.lowlevel.rotation as rotation

from droidlet.lowlevel.hello_robot.hello_robot_mover import HelloRobotMover
from droidlet.event import sio

faulthandler.register(signal.SIGUSR1)

random.seed(0)
log_formatter = logging.Formatter(
    "%(asctime)s [%(filename)s:%(lineno)s - %(funcName)s() %(levelname)s]: %(message)s"
)
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().handlers.clear()


class HelloRobotAgent(LocoMCAgent):
    """Implements an instantiation of the LocoMCAgent on a Hello Robot Stretch RE1. It starts
    off the agent processes including launching the dashboard.

    Args:
        opts (argparse.Namespace): opts returned by the ArgumentParser with defaults set
            that you can override.
        name (string, optional): a name for your agent (default: Locobot)

    Example:
        >>> python hello_robot_agent.py'
    """

    coordinate_transforms = rotation

    def __init__(self, opts, name="HelloRobot"):
        super(HelloRobotAgent, self).__init__(opts)
        logging.info("HelloRobotAgent.__init__ started")
        self.opts = opts
        self.entityId = 0
        self.no_default_behavior = opts.no_default_behavior
        self.last_chat_time = -1000000000000
        self.name = name
        self.player = Player(100, name, Pos(0, 0, 0), Look(0, 0))
        self.pos = Pos(0, 0, 0)
        self.uncaught_error_count = 0
        self.last_task_memid = None
        self.point_targets = []
        self.init_event_handlers()
        # list of (prob, default function) pairs
        self.visible_defaults = [(1.0, default_behaviors.explore)]

    def init_event_handlers(self):
        super().init_event_handlers()

        @sio.on("command")
        def test_command(sid, commands):
            for command in commands:
                if command == "MOVE_FORWARD":
                    self.mover.bot.translate_by(0.1)
                    print("action: FORWARD")
                elif command == "MOVE_BACKWARD":
                    self.mover.bot.translate_by(-0.1)
                    print("action: BACKWARD")
                elif command == "MOVE_LEFT":
                    self.mover.bot.rotate_by(0.2)
                    print("action: LEFT")
                elif command == "MOVE_RIGHT":
                    self.mover.bot.rotate_by(-0.2)
                    print("action: RIGHT")
                elif command == "PAN_LEFT":
                    self.mover.bot.set_pan(self.mover.bot.get_pan() + 0.08)
                elif command == "PAN_RIGHT":
                    self.mover.bot.set_pan(self.mover.bot.get_pan() - 0.08)
                elif command == "TILT_UP":
                    self.mover.bot.set_tilt(self.mover.bot.get_tilt() - 0.08)
                elif command == "TILT_DOWN":
                    self.mover.bot.set_tilt(self.mover.bot.get_tilt() + 0.08)

        @sio.on("shutdown")
        def _shutdown(sid, data):
            self.shutdown()

    def init_memory(self):
        """Instantiates memory for the agent.

        Uses the DB_FILE environment variable to write the memory to a
        file or saves it in-memory otherwise.
        """
        self.memory = LocoAgentMemory(
            db_file=os.environ.get("DB_FILE", ":memory:"),
            db_log_path=None,
            coordinate_transforms=self.coordinate_transforms,
        )
        dance.add_default_dances(self.memory)
        logging.info("Initialized agent memory")

    def init_perception(self):
        """Instantiates all perceptual modules.

        Each perceptual module should have a perceive method that is
        called by the base agent event loop.
        """
        if not hasattr(self, "perception_modules"):
            self.perception_modules = {}
        self.perception_modules["self"] = SelfPerception(self)
        self.perception_modules["vision"] = Perception(self, self.opts.perception_model_dir)

    def init_controller(self):
        """Instantiates controllers - the components that convert a text chat to task(s)."""
        dialogue_object_classes = {}
        dialogue_object_classes["bot_capabilities"] = LocoBotCapabilities
        dialogue_object_classes["interpreter"] = LocoInterpreter
        dialogue_object_classes["get_memory"] = LocoGetMemoryHandler
        dialogue_object_classes["put_memory"] = PutMemoryHandler
        self.dialogue_manager = DialogueManager(
            memory=self.memory,
            dialogue_object_classes=dialogue_object_classes,
            semantic_parsing_model_wrapper=DroidletNSPModelWrapper,
            opts=self.opts,
        )

    def init_physical_interfaces(self):
        """Instantiates the interface to physically move the robot."""
        self.mover = HelloRobotMover(ip=self.opts.ip)

    def get_player_struct_by_name(self, speaker_name):
        p = self.memory.get_player_by_name(speaker_name)
        if p:
            return p.get_struct()
        else:
            return None

    def get_other_players(self):
        return [self.player]

    def get_incoming_chats(self):
        all_chats = []
        speaker_name = "dashboard"
        if self.dashboard_chat is not None:
            if not self.memory.get_player_by_name(speaker_name):
                PlayerNode.create(
                    self.memory,
                    to_player_struct((None, None, None), None, None, None, speaker_name),
                )
            all_chats.append(self.dashboard_chat)
            self.dashboard_chat = None
        return all_chats

    # # FIXME!!!!
    def send_chat(self, chat: str):
        logging.info("Sending chat: {}".format(chat))
        # Send the socket event to show this reply on dashboard
        sio.emit("showAssistantReply", {"agent_reply": "Agent: {}".format(chat)})
        self.memory.add_chat(self.memory.self_memid, chat)
        # actually send the chat, FIXME FOR HACKATHON
        # return self._cpp_send_chat(chat)

    def step(self):
        super().step()
        time.sleep(0)

    def task_step(self, sleep_time=0.0):
        super().task_step(sleep_time=sleep_time)

    def shutdown(self):
        self._shutdown = True
        self.perception_modules["vision"].vprocess_shutdown.set()


if __name__ == "__main__":
    base_path = os.path.dirname(__file__)
    parser = ArgumentParser("Locobot", base_path)
    opts = parser.parse()

    logging.basicConfig(level=opts.log_level.upper())
    # set up stdout logging
    sh = logging.StreamHandler()
    sh.setFormatter(log_formatter)
    logger = logging.getLogger()
    logger.addHandler(sh)
    logging.info("LOG LEVEL: {}".format(logger.level))

    # Check that models and datasets are up to date
    if not opts.dev:
        rc = subprocess.call([opts.verify_hash_script_path, "hello_robot"])

    set_start_method("spawn", force=True)

    sa = HelloRobotAgent(opts)
    sa.start()
