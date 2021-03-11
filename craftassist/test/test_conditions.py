"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import unittest

from copy import deepcopy
from base_craftassist_test_case import BaseCraftassistTestCase
from base_agent.test.all_test_commands import *
from fake_mobs import LoopMob, make_mob_opts
from base_agent.base_util import TICKS_PER_SEC


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
        self.set_looking_at((1, 63, -2))
        d = STOP_CONDITION_COMMANDS["go left until that cow is closer than 2 steps to me"]
        self.handle_logical_form(d, max_steps=1000)
        self.assertLessEqual(((5 - cow.pos[0]) ** 2 + (5 - cow.pos[2]) ** 2) ** 0.5, 2)
        self.assertLessEqual(self.agent.pos[2], -10)
        self.assertLessEqual(abs(self.agent.pos[0]), 1)


#        self.assertLessEqual(abs(self.agent.pos[0] - 5), 1.01)


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


if __name__ == "__main__":
    unittest.main()
