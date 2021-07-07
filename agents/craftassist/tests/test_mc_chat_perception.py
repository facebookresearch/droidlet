"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import numpy as np
from typing import List
import unittest

from ..craftassist_agent import CraftAssistAgent
from droidlet.lowlevel.minecraft.mc_util import XYZ, IDM, Block
from droidlet.memory.craftassist.mc_memory import MCAgentMemory
from droidlet.perception.craftassist.rotation import yaw_pitch
from droidlet.shared_data_structs import MockOpt
from .fake_agent import FakeAgent, FakePlayer, FakeMCTime
from .utils import Player, Pos, Look, Item, Look
from .world import World, Opt, flat_ground_generator

HEAD_HEIGHT = 2

class FakeMCAgent(CraftAssistAgent):
    """This FakeMCAgent preserves the original perceive() fn of CraftAssistAgent
    """
    def __init__(self, world, opts):
        self.world = world
        self.opts = opts
        self.chat_count = 0
        super(FakeMCAgent, self).__init__(opts)
        pos = (0, 63, 0)
        if hasattr(self.world, "agent_data"):
            pos = self.world.agent_data["pos"]
        self.pos = np.array(pos, dtype="int")
        self._look_vec = (1, 0, 0)
        self._held_item: IDM = (0, 0)
        self._changed_blocks: List[Block] = []
        self.add_self_memory_node()

    def init_memory(self):
        T = FakeMCTime(self.world)
        self.memory = MCAgentMemory(
            load_minecraft_specs=False,
            agent_time=T,
        )
    
    def get_look(self):
        yaw, pitch = yaw_pitch(self._look_vec)
        return Look(yaw, pitch)

    def get_incoming_chats(self):
        c = self.chat_count
        self.chat_count = len(self.world.chat_log)
        return self.world.chat_log[c:].copy()
    
    def get_player(self):
        return Player(1, "fake_agent", Pos(*self.pos), self.get_look(), Item(*self._held_item))
    
    def get_other_players(self):
        return self.world.get_players()
    
    def get_mobs(self):
        return self.world.get_mobs()
    
    def get_item_stacks(self):
        return self.world.get_item_stacks()
    
    def get_player_line_of_sight(self, player_struct):
        if hasattr(self.world, "get_line_of_sight"):
            pos = (player_struct.pos.x, player_struct.pos.y + HEAD_HEIGHT, player_struct.pos.z)
            pitch = player_struct.look.pitch
            yaw = player_struct.look.yaw
            xsect = self.world.get_line_of_sight(pos, yaw, pitch)
            if xsect is not None:
                return Pos(*xsect)
        else:
            raise NotImplementedError()
        
    def get_changed_blocks(self) -> List[Block]:
        # need a better solution here
        r = self._changed_blocks.copy()
        self._changed_blocks.clear()
        return r

    def safe_get_changed_blocks(self) -> List[Block]:
        return self.get_changed_blocks()
    
    def get_blocks(self, xa, xb, ya, yb, za, zb):
        return self.world.get_blocks(xa, xb, ya, yb, za, zb)


class TestMCChatPerception(unittest.TestCase):
    """This class tests perceive fn in CraftAssistAgent. It pushes some chat message to the world
    and check if chat_parser can correctly parse it and put all relevant info into memory
    It then checks the number of logical forms stored in memory (for each new chat, there should
    be one more logical form stored in memory)
    """
    def __init__(self, *args, **kwargs):
        super(TestMCChatPerception, self).__init__(*args, **kwargs)
        opts = MockOpt()
        players = [
            FakePlayer(
                Player(42, "SPEAKER", Pos(5, 63, 5), Look(270, 0), Item(0, 0)), active=False
            )
        ]
        spec = {
            "players": players,
            "mobs": [],
            "item_stacks": [],
            "ground_generator": flat_ground_generator,
            "agent": {"pos": (0, 63, 0)},
            "coord_shift": (-16, 54, -16),
        }
        world_opts = Opt()
        world_opts.sl = 32
        self.world = World(world_opts, spec)
        self.agent = FakeMCAgent(self.world, opts)
        self.speaker = self.agent.get_other_players()[0].name
        self.agent.perceive()
    
    def test_chat_perception(self):
        
        lf_num = self.agent.memory.get_triples(pred_text="has_logical_form")
        self.assertEqual(len(lf_num), 0)

        self.agent.world.add_incoming_chat("hello", self.speaker)
        self.agent.perceive()
        lf_num = self.agent.memory.get_triples(pred_text="has_logical_form")
        self.assertEqual(len(lf_num), 1)

        self.agent.world.add_incoming_chat("build a cube", self.speaker)
        self.agent.perceive()
        lf_num = self.agent.memory.get_triples(pred_text="has_logical_form")
        self.assertEqual(len(lf_num), 2)
