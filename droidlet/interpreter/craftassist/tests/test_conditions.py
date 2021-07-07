"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import unittest
import numpy as np

from droidlet.interpreter.tests.all_test_commands import *
from droidlet.base_util import TICKS_PER_SEC
from agents.craftassist.tests.base_craftassist_test_case import BaseCraftassistTestCase
from agents.craftassist.tests.fake_mobs import LoopMob, make_mob_opts


def add_sequence_mob(test, mobname, sequence):
    m = LoopMob(make_mob_opts(mobname), sequence)
    m.add_to_world(test.world)


class MoveDirectionUntilTest(BaseCraftassistTestCase):
    def setUp(self):
        super().setUp()

    def test_move_till_condition(self):
        cow_look = (0.0, 0.0)
        x = -5
        z = -5
        cow_move_sequence = [((x, 63, z), cow_look)]
        # speaker_pos = [5, 63, 5]
        for i in range(20):
            while x < 10:
                x += 1
                cow_move_sequence.append(((x, 63, z), cow_look))
                z += 1
                cow_move_sequence.append(((x, 63, z), cow_look))
            while x > 1:
                x -= 1
                cow_move_sequence.append(((x, 63, z), cow_look))
                z -= 1
                cow_move_sequence.append(((x, 63, z), cow_look))

        add_sequence_mob(self, "cow", cow_move_sequence)
        cow = self.agent.world.mobs[0]
        look_at_target = (1, 63, -2)
        self.set_looking_at(look_at_target)

        d = STOP_CONDITION_COMMANDS["go left until that cow is closer than 2 steps to me"]
        self.handle_logical_form(d, max_steps=1000)

        # check stopped when cow was close:
        self.assertLessEqual(((5 - cow.pos[0]) ** 2 + (5 - cow.pos[2]) ** 2) ** 0.5, 2)

        # check agent went left:
        player_lv = np.array(look_at_target) - np.array((5, 63, 5))
        player_lv = player_lv / np.linalg.norm(player_lv)
        player_left = player_lv.copy()
        player_left[0] = player_lv[2]
        player_left[2] = -player_lv[0]
        agent_mv = self.agent.pos - np.array((0, 63, 0))
        agent_mv_n = agent_mv / np.linalg.norm(agent_mv)
        self.assertGreaterEqual(agent_mv_n @ player_left, 0.8)

        # check that player stopped first time cow was close:
        self.assertLessEqual(self.agent.world.count, 30)


class FollowUntilTest(BaseCraftassistTestCase):
    def setUp(self):
        super().setUp()

    def test_move_till_condition(self):
        cow_look = (0.0, 0.0)
        cow_move_sequence = [((0, 63, 0), cow_look)]
        x = 0
        for i in range(20):
            while x < 10:
                x += 1
                for j in [-2, -3, -2, -3]:
                    cow_move_sequence.append(((x, 63, j), cow_look))
            while x > 1:
                x -= 1
                for j in [-2, -3, -2, -3]:
                    cow_move_sequence.append(((x, 63, j), cow_look))

        add_sequence_mob(self, "cow", cow_move_sequence)
        cow = self.agent.world.mobs[0]
        self.set_looking_at((1, 63, -2))

        d = deepcopy(STOP_CONDITION_COMMANDS["follow the cow for 18 seconds"])
        start_time = self.agent.get_time()
        self.handle_logical_form(d, max_steps=5000)
        end_time = self.agent.get_time()
        time_elapsed = (end_time - start_time) / TICKS_PER_SEC
        self.assertLessEqual(
            abs(self.agent.pos[0] - cow.pos[0]) + abs(self.agent.pos[2] - cow.pos[2]), 1.01
        )
        self.assertLessEqual(time_elapsed, 20)
        self.assertGreaterEqual(time_elapsed, 16)

        d = deepcopy(STOP_CONDITION_COMMANDS["follow the cow for 2 minutes"])
        start_time = self.agent.get_time()
        self.handle_logical_form(d, max_steps=5000)
        end_time = self.agent.get_time()
        time_elapsed = (end_time - start_time) / TICKS_PER_SEC
        self.assertLessEqual(
            abs(self.agent.pos[0] - cow.pos[0]) + abs(self.agent.pos[2] - cow.pos[2]), 1.01
        )
        self.assertLessEqual(time_elapsed, 130)
        self.assertGreaterEqual(time_elapsed, 110)


#        # FIXME!!!!  this test is flaky....
#        # TODO make sure cow is moving in x positive direction from below 5 when the test starts
#        # it is now if everything else works, but should force it
#        d = deepcopy(
#            STOP_CONDITION_COMMANDS["follow the cow for 18 seconds after it has x greater than 5"]
#        )
#        start_time = self.agent.get_time()
#        self.handle_logical_form(d, max_steps=5000)
#        end_time = self.agent.get_time()
#        time_elapsed = (end_time - start_time) / TICKS_PER_SEC
#        self.assertEqual(cow_move_sequence[self.agent.world.count - 1 - 18][0][0], 6)
#        self.assertLessEqual(
#            abs(self.agent.pos[0] - cow.pos[0]) + abs(self.agent.pos[2] - cow.pos[2]), 1.01
#        )

class DigRemoveConditionTest(BaseCraftassistTestCase):
    def setUp(self):
        super().setUp()

    def test_dig_n_times(self):
        s  = deepcopy(STOP_CONDITION_COMMANDS["dig a hole 2 times"])
        changes = self.handle_logical_form(d)
        

if __name__ == "__main__":
    unittest.main()
