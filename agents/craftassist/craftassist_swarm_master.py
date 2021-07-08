"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from agents.craftassist import craftassist_swarm_worker
import os
import logging
import faulthandler
from pickle import NONE
import signal
import random
import sentry_sdk
import time
from multiprocessing import set_start_method
from collections import namedtuple
import subprocess

# `from craftassist.agent` instead of `from .` because this file is
# also used as a standalone script and invoked via `python craftassist_agent.py`
from agents.craftassist.craftassist_swarm_worker import CraftAssist_SwarmWorker, CraftAssist_SwarmWorker_Wrapper
from droidlet.interpreter.craftassist import default_behaviors, inventory, dance
from droidlet.memory.craftassist import mc_memory
from droidlet.perception.craftassist import rotation, heuristic_perception
from droidlet.lowlevel.minecraft.shapes import SPECIAL_SHAPE_FNS
import droidlet.dashboard as dashboard

if __name__ == "__main__":
    # this line has to go before any imports that contain @sio.on functions
    # or else, those @sio.on calls become no-ops
    print("starting dashboard...")
    dashboard.start()

from droidlet.dialog.swarm_dialogue_manager import DialogueManager
from droidlet.dialog.map_to_dialogue_object import DialogueObjectMapper
from droidlet.base_util import Pos, Look
from agents.loco_mc_agent import LocoMCAgent
from droidlet.memory.memory_nodes import PlayerNode
from droidlet.perception.semantic_parsing.nsp_querier import NSPQuerier
from agents.argument_parser import ArgumentParser
from droidlet.dialog.craftassist.dialogue_objects import MCBotCapabilities
from droidlet.interpreter.craftassist import MCGetMemoryHandler, PutMemoryHandler, MCInterpreter, SwarmMCInterpreter
from droidlet.perception.craftassist.low_level_perception import LowLevelMCPerception
from droidlet.lowlevel.minecraft.mc_agent import Agent as MCAgent
from droidlet.lowlevel.minecraft.mc_util import cluster_areas, MCTime, SPAWN_OBJECTS
from droidlet.perception.craftassist.voxel_models.subcomponent_classifier import (
    SubcomponentClassifierWrapper,
)
from droidlet.lowlevel.minecraft import craftassist_specs
from droidlet.interpreter.craftassist import swarm_tasks
from multiprocessing import Queue
from craftassist_swarm_worker import TASK_MAP
import pdb

faulthandler.register(signal.SIGUSR1)

random.seed(0)
log_formatter = logging.Formatter(
    "%(asctime)s [%(filename)s:%(lineno)s - %(funcName)s() %(levelname)s]: %(message)s"
)
logging.getLogger().handlers.clear()

sentry_sdk.init()  # enabled if SENTRY_DSN set in env
DEFAULT_BEHAVIOUR_TIMEOUT = 20
DEFAULT_FRAME = "SPEAKER"
Player = namedtuple("Player", "entityId, name, pos, look, mainHand")
Item = namedtuple("Item", "id, meta")


class CraftAssist_SwarmMaster(LocoMCAgent):
    default_frame = DEFAULT_FRAME
    coordinate_transforms = rotation
    default_num_agents = 3

    def __init__(self, opts):
        self.low_level_data = {"mobs": SPAWN_OBJECTS,
                               "mob_property_data": craftassist_specs.get_mob_property_data(),
                               "schematics": craftassist_specs.get_schematics(),
                               "block_data": craftassist_specs.get_block_data(),
                               "block_property_data": craftassist_specs.get_block_property_data(),
                               "color_data": craftassist_specs.get_colour_data()
                               }

        try:
            self.num_agents = opts.num_agents
        except:
            logging.info("Default swarm with {} agents.".format(self.default_num_agents))
            self.num_agents = self.default_num_agents
        self.swarm_workers = [CraftAssist_SwarmWorker_Wrapper(opts, idx=i) for i in range(self.num_agents - 1)]

        super(CraftAssist_SwarmMaster, self).__init__(opts)
        self.no_default_behavior = opts.no_default_behavior
        self.point_targets = []
        self.last_chat_time = 0
        # areas must be perceived at each step
        # List of tuple (XYZ, radius), each defines a cube
        self.areas_to_perceive = []
        self.add_self_memory_node()
        self.init_inventory()
        self.init_event_handlers()

        # list of (prob, default function) pairs
        self.visible_defaults = [
            (0.001, default_behaviors.build_random_shape),
            (0.005, default_behaviors.come_to_player),
        ]
        self.perceive_on_chat = True

        self.swarm_task_queue = [Queue() for i in range(self.num_agents - 1)]

    def assign_task_to_worker(self, i, task_name, task_data):
        if i == 0:
            TASK_MAP[task_name](self, task_data)
        else:
            self.swarm_workers[i-1].input_tasks.put((task_name, task_data))

    def get_chats(self):
        """This function is a wrapper around self.cagent.get_incoming_chats and adds a new
        chat self.dashboard_chat which is set by the dashboard."""
        all_chats = self.cagent.get_incoming_chats()
        updated_chats = []
        if self.dashboard_chat:
            updated_chats.append(self.dashboard_chat)
            self.dashboard_chat = None
        updated_chats.extend(all_chats)
        return updated_chats

    def get_all_players(self):
        """This function is a wrapper around self.cagent.get_other_players and adds a new
        player called "dashboard" if it doesn't already exist."""
        all_players = self.cagent.get_other_players()
        updated_players = all_players
        player_exists = False
        for player in all_players:
            if player.name == "dashboard":
                player_exists = True
        if not player_exists:
            newPlayer = Player(
                12345678, "dashboard", Pos(0.0, 64.0, 0.0), Look(0.0, 0.0), Item(0, 0)
            )
            updated_players.append(newPlayer)
        return updated_players

    def get_all_player_line_of_sight(self, player_struct):
        """return a fixed value for "dashboard" player"""
        if isinstance(player_struct, Player):
            return Pos(-1, 63, 14)
        return self.cagent.get_player_line_of_sight(player_struct)

    def init_event_handlers(self):
        """Handle the socket events"""
        super().init_event_handlers()

    def init_inventory(self):
        """Initialize the agent's inventory"""
        self.inventory = inventory.Inventory()
        logging.info("Initialized agent inventory")

    def init_memory(self):
        """Intialize the agent memory and logging."""
        self.memory = mc_memory.MCAgentMemory(
            db_file=os.environ.get("DB_FILE", ":memory:"),
            coordinate_transforms=self.coordinate_transforms,
            db_log_path="agent_memory.{}.log".format(self.name),
            agent_time=MCTime(self.get_world_time),
            agent_low_level_data=self.low_level_data,
        )
        # Add all dances to memory
        dance.add_default_dances(self.memory)
        file_log_handler = logging.FileHandler("agent.{}.log".format(self.name))
        file_log_handler.setFormatter(log_formatter)
        logging.getLogger().addHandler(file_log_handler)
        logging.info("Initialized agent memory")

    def init_perception(self):
        """Initialize perception modules"""
        # NOTE: self.chat_parser will move to perception_modules once Soumith's changes are in
        self.chat_parser = NSPQuerier(self.opts)
        self.perception_modules = {}
        self.perception_modules["low_level"] = LowLevelMCPerception(self)
        self.perception_modules["heuristic"] = heuristic_perception.PerceptionWrapper(
            self, low_level_data=self.low_level_data
        )
        # set up the SubComponentClassifier model
        if os.path.isfile(self.opts.semseg_model_path):
            self.perception_modules["semseg"] = SubcomponentClassifierWrapper(
                self, self.opts.semseg_model_path
            )

        self.on_demand_perception = {}
        self.on_demand_perception["check_inside"] = heuristic_perception.check_inside

    def init_controller(self):
        """Initialize all controllers"""
        dialogue_object_classes = {}
        dialogue_object_classes["bot_capabilities"] = MCBotCapabilities
        dialogue_object_classes["interpreter"] = SwarmMCInterpreter
        dialogue_object_classes["get_memory"] = MCGetMemoryHandler
        dialogue_object_classes["put_memory"] = PutMemoryHandler
        self.opts.block_data = craftassist_specs.get_block_data()
        self.opts.special_shape_functions = SPECIAL_SHAPE_FNS
        # use swarm dialogue manager that does not track its own swarm behaviorss
        self.dialogue_manager = DialogueManager(
            memory=self.memory,
            dialogue_object_classes=dialogue_object_classes,
            dialogue_object_mapper=DialogueObjectMapper,
            # swarm_workers_names=self.names,
            opts=self.opts,
        )

    # def task_step(self, sleep_time=0.25):
    #     super().task_step(sleep_time)
    #     # for worker in self.swarm_workers:
    #     #     worker.task_step(sleep_time)

    def start(self):
        # count forever unless the shutdown signal is given
        for swarm_worker in self.swarm_workers:
            swarm_worker.start()
        
        while not self._shutdown:
            try:
                self.step()
            except Exception as e:
                self.handle_exception(e)
        
    def perceive(self, force=False):
        """Whenever some blocks are changed, that area will be put into a 
        buffer which will be force-perceived by the agent in the next step

        Here the agent first clusters areas that are overlapping on the buffer,
        then run through all perception modules to perceive
        and finally clear the buffer when perception is done.
        """
        self.areas_to_perceive = cluster_areas(self.areas_to_perceive)
        super().perceive()
        self.areas_to_perceive = []
        # for worker in self.swarm_workers:
        #     worker.perceive()


    def get_time(self):
        """round to 100th of second, return as
        n hundreth of seconds since agent init.
        Returns:
            Current time in the world.
        """
        return self.memory.get_time()

    def get_world_time(self):
        """MC time is based on ticks, where 20 ticks happen every second.
        There are 24000 ticks in a day, making Minecraft days exactly 20 minutes long.
        The time of day in MC is based on the timestamp modulo 24000 (default).
        0 is sunrise, 6000 is noon, 12000 is sunset, and 18000 is midnight.

        Returns:
            Time of day based on above
        """
        return self.get_time_of_day()

    def safe_get_changed_blocks(self):
        """Get all blocks that have been changed.
        Returns:
            List of changed blocks
        """
        blocks = self.cagent.get_changed_blocks()
        safe_blocks = []
        if len(self.point_targets) > 0:
            for point_target in self.point_targets:
                pt = point_target[0]
                for b in blocks:
                    x, y, z = b[0]
                    xok = x < pt[0] or x > pt[3]
                    yok = y < pt[1] or y > pt[4]
                    zok = z < pt[2] or z > pt[5]
                    if xok and yok and zok:
                        safe_blocks.append(b)
        else:
            safe_blocks = blocks
        return safe_blocks

    def point_at(self, target, agent_idx=None, agent_name=None, sleep=None):
        """Bot pointing.

        Args:
            target: list of x1 y1 z1 x2 y2 z2, where:
                    x1 <= x2,
                    y1 <= y2,
                    z1 <= z2.
        """
        assert len(target) == 6
        agent_idx = self.get_agent_idx(agent_idx, agent_name)
        if agent_idx is None:
            return
        self.send_chat("/point {} {} {} {} {} {}".format(*target), agent_idx=agent_idx)
        self.point_targets.append((target, time.time()))
        # sleep before the bot can take any actions
        # otherwise there might be bugs since the object is flashing
        # deal with this in the task...
        if sleep:
            time.sleep(sleep)

    def relative_head_pitch(self, angle):
        """Converts assistant's current pitch and yaw
        into a pitch and yaw relative to the angle."""
        # warning: pitch is flipped!
        for i in range(self.num_agents):
            new_pitch = self.get_player[i]().look.pitch - angle
            self.set_look[i](self.get_player[i]().look.yaw, new_pitch)

    def send_chat(self, chat, agent_idx=None, agent_name=None):
        """Send chat from agent to player"""
        agent_idx = self.get_agent_idx(agent_idx, agent_name)
        if agent_idx is None:
            return
        elif agent_idx == 0:
            logging.info("{} Sending chat: {}".format(self.name, chat))
            self.memory.add_chat(self.memory.self_memid, chat)
            return self.cagent.send_chat(chat)
        else:
            self.swarm_workers[agent_idx-1].input_chat.put(chat)

    # TODO update client so we can just loop through these
    # TODO rename things a bit- some perceptual things are here,
    #      but under current abstraction should be in init_perception
    def init_physical_interfaces(self):
        """Initializes the physical interfaces of the agent."""
        # For testing agent without cuberite server

        if self.opts.port == -1:
            return
        logging.info("Attempting to connect to port {}".format(self.opts.port))
        
        # create a swarm of agents
        self.names = [self.name]
        for i in range(self.num_agents - 1):
            self.names.append(self.swarm_workers[i].name)

        # agent 0 is the master agent, the others are worker/sub agents
        # self.cagent = self.swarm_workers[0].agent.cagent
        self.cagent = MCAgent("localhost", self.opts.port, self.name)

        self.dig = self.cagent.dig
        self.drop_item_stack_in_hand = self.cagent.drop_item_stack_in_hand
        self.drop_item_in_hand = self.cagent.drop_item_in_hand
        self.drop_inventory_item_stack = self.cagent.drop_inventory_item_stack
        self.set_inventory_slot = self.cagent.set_inventory_slot
        self.get_player_inventory = self.cagent.get_player_inventory
        self.get_inventory_item_count = self.cagent.get_inventory_item_count
        self.get_inventory_items_counts = self.cagent.get_inventory_items_counts
        # defined above...
        # self.send_chat = self.cagent.send_chat
        self.set_held_item = self.cagent.set_held_item
        self.step_pos_x = self.cagent.step_pos_x
        self.step_neg_x = self.cagent.step_neg_x
        self.step_pos_z = self.cagent.step_pos_z
        self.step_neg_z = self.cagent.step_neg_z
        self.step_pos_y = self.cagent.step_pos_y
        self.step_neg_y = self.cagent.step_neg_y
        self.step_forward = self.cagent.step_forward
        self.look_at = self.cagent.look_at
        self.set_look = self.cagent.set_look
        self.turn_angle = self.cagent.turn_angle
        self.turn_left = self.cagent.turn_left
        self.turn_right = self.cagent.turn_right
        self.place_block = self.cagent.place_block
        self.use_entity = self.cagent.use_entity
        self.use_item = self.cagent.use_item
        self.use_item_on_block = self.cagent.use_item_on_block
        self.is_item_stack_on_ground = self.cagent.is_item_stack_on_ground
        self.craft = self.cagent.craft
        self.get_blocks = self.cagent.get_blocks
        self.get_local_blocks = self.cagent.get_local_blocks
        self.get_incoming_chats = self.get_chats
        self.get_player = self.cagent.get_player
        self.get_mobs = self.cagent.get_mobs
        self.get_other_players = self.get_all_players
        self.get_other_player_by_name = self.cagent.get_other_player_by_name
        self.get_vision = self.cagent.get_vision
        self.get_line_of_sight = self.cagent.get_line_of_sight
        self.get_player_line_of_sight = self.get_all_player_line_of_sight
        self.get_changed_blocks = self.cagent.get_changed_blocks
        self.get_item_stacks = self.cagent.get_item_stacks
        self.get_world_age = self.cagent.get_world_age
        self.get_time_of_day = self.cagent.get_time_of_day
        self.get_item_stack = self.cagent.get_item_stack

    def add_self_memory_node(self):
        """Adds agent node into its own memory"""
        # how/when to, memory is initialized before physical interfaces...
        # TODO: check if using player 0 works
        try:
            p = self.get_player()
        except:  # this is for test/test_agent
            return
        PlayerNode.create(self.memory, p, memid=self.memory.self_memid)

    def get_agent_idx(self, agent_idx, agent_name):
        if agent_idx is None:
            if agent_name is None:
                agent_idx = 0
            else:
                try:
                    agent_idx = self.names.index(agent_name)
                except:
                    logging.info("agent name not found.")
                    # return None
                    return 0
        return agent_idx

if __name__ == "__main__":
    base_path = os.path.dirname(__file__)
    parser = ArgumentParser("Minecraft", base_path)
    opts = parser.parse()

    logging.basicConfig(level=opts.log_level.upper())

    # set up stdout logging
    sh = logging.StreamHandler()
    sh.setFormatter(log_formatter)
    logger = logging.getLogger()
    logger.addHandler(sh)
    logging.info("LOG LEVEL: {}".format(logger.level))

    # Check that models and datasets are up to date and download latest resources.
    # Also fetches additional resources for internal users.
    if not opts.dev:
        rc = subprocess.call([opts.verify_hash_script_path, "craftassist"])

    set_start_method("spawn", force=True)

    sa = CraftAssist_SwarmMaster(opts)
    sa.start()
