"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import unittest
from unittest.mock import Mock
import numpy as np
from typing import List, Sequence, Dict

from droidlet.memory.craftassist.mc_memory_nodes import VoxelObjectNode
from droidlet.lowlevel.minecraft.mc_util import XYZ, Block, IDM
from droidlet.perception.craftassist.rotation import yaw_pitch
from droidlet.dialog.dialogue_objects import AwaitResponse

from .fake_agent import FakeAgent, FakePlayer
from .utils import Player, Pos, Look, Item, Look, to_relative_pos
from .world import World, Opt, flat_ground_generator


class BaseCraftassistTestCase(unittest.TestCase):
    def setUp(self, agent_opts=None, players=[]):
        if not players:
            players = [
                FakePlayer(
                    Player(42, "SPEAKER", Pos(5, 63, 5), Look(270, 0), Item(0, 0)),
                    active=False,
                    opts=agent_opts,
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
        self.agent = FakeAgent(self.world, opts=agent_opts)
        self.set_looking_at((0, 63, 0))
        self.speaker = self.agent.get_other_players()[0].name
        self.agent.perceive()
        self.num_steps = 0

    def handle_logical_form(
        self, d, chatstr: str = "", answer: str = None, stop_on_chat=False, max_steps=10000
    ) -> Dict[XYZ, IDM]:
        """Handle a logical form and call self.flush()

        If "answer" is specified and a question is asked by the agent, respond
        with this string.

        If "stop_on_chat" is specified, stop iterating if the agent says anything
        """
        chatstr = chatstr or "TEST {}".format(d)
        self.add_incoming_chat(chatstr, self.speaker)
        self.agent.set_logical_form(d, chatstr, self.speaker)
        changes = self.flush(max_steps, stop_on_chat=stop_on_chat)
        if len(self.agent.dialogue_manager.dialogue_stack) != 0 and answer is not None:
            self.add_incoming_chat(answer, self.speaker)
            changes.update(self.flush(max_steps, stop_on_chat=stop_on_chat))
        return changes

    def flush(self, max_steps=10000, stop_on_chat=False) -> Dict[XYZ, IDM]:
        """Run the agant's step until task and dialogue stacks are empty

        If "stop_on_chat" is specified, stop iterating if the agent says anything

        Return the set of blocks that were changed.
        """

        if stop_on_chat:
            self.agent.clear_outgoing_chats()

        world_before = self.agent.world.blocks_to_dict()

        for i in range(max_steps):
            self.agent.step()
            if self.agent_should_stop(stop_on_chat):
                break

        # get changes
        world_after = self.world.blocks_to_dict()
        changes = dict(set(world_after.items()) - set(world_before.items()))
        changes.update({k: (0, 0) for k in set(world_before.keys()) - set(world_after.keys())})
        if i == max_steps - 1:
            print("warning in {} : agent ran till max_steps".format(self))
        return changes

    def agent_should_stop(self, stop_on_chat=False):
        stop = False
        if (
            len(self.agent.dialogue_manager.dialogue_stack) == 0
            and not self.agent.memory.task_stack_peek()
        ):
            stop = True
        # stuck waiting for answer?
        if (
            isinstance(self.agent.dialogue_manager.dialogue_stack.peek(), AwaitResponse)
            and not self.agent.dialogue_manager.dialogue_stack.peek().finished
        ):
            stop = True
        if stop_on_chat and self.agent.get_last_outgoing_chat():
            stop = True
        return stop

    def set_looking_at(self, xyz: XYZ, player=None):
        """
        sets the look of the given player (or the first one from agent.get_other_players())
        player if given should be a Player struct.

        warning: previous incarnation of this mocked the agent's
        get_player_line_of_sight.  This new version will be "fooled"
        if something is in between the player and the target xyz;
        and uses the agent's world's get_line_of_sight
        """
        player = player or self.agent.world.players[0]
        player.look_at(*xyz)

    def set_blocks(self, xyzbms: List[Block], origin: XYZ = (0, 0, 0)):
        self.agent.set_blocks(xyzbms, origin)

    def add_object(
        self, xyzbms: List[Block], origin: XYZ = (0, 0, 0), relations={}
    ) -> VoxelObjectNode:
        return self.agent.add_object(xyzbms=xyzbms, origin=origin, relations=relations)

    def add_incoming_chat(self, chat: str, speaker_name: str):
        """Add a chat to memory as if it was just spoken by SPEAKER"""
        self.world.chat_log.append("<" + speaker_name + ">" + " " + chat)

    #        self.agent.memory.add_chat(self.agent.memory.get_player_by_name(self.speaker).memid, chat)

    def assert_schematics_equal(self, a, b):
        """Check equality between two list[(xyz, idm)] schematics

        N.B. this compares the shapes and idms, but ignores absolute position offsets.
        """
        a, _ = to_relative_pos(a)
        b, _ = to_relative_pos(b)
        self.assertEqual(set(a), set(b))

    def get_idm_at_locs(self, xyzs: Sequence[XYZ]) -> Dict[XYZ, IDM]:
        return self.world.get_idm_at_locs(xyzs)

    def last_outgoing_chat(self) -> str:
        return self.agent.get_last_outgoing_chat()

    def get_speaker_pos(self) -> XYZ:
        return self.agent.memory.get_player_by_name(self.speaker).pos
