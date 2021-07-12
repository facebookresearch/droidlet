"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import unittest

import numpy as np

from droidlet.interpreter.robot.tests.base_fakeagent_test_case import BaseFakeAgentTestCase
import droidlet.lowlevel.rotation as rotation
from droidlet.interpreter.tests.all_test_commands import MOVE_COMMANDS
from droidlet.perception.semantic_parsing.tests.test_y_print_parsing_report import GROUND_TRUTH_PARSES
from droidlet.lowlevel.locobot.tests.test_utils import assert_turn_degree

CUBE1 = (9, 0, 4)
CUBE2 = (9, 0, 10)
TOY = (2, 0, 4)
CAMERA_HEIGHT = 1.0


def add_two_cubes(test):
    test.agent.add_object(CUBE1, tags=["cube", "_physical_object"])
    test.agent.add_object(CUBE2, tags=["cube", "_physical_object"])


def add_a_toy(test):
    test.agent.add_object(TOY, tags=["toy", "_physical_object"])


#    test.set_looking_at(test.cube_right[0][0])


class MoveAbsoluteTest(BaseFakeAgentTestCase):
    """Test for Move."""

    def assert_move(self, reldir, steps, changes):
        old_pos = changes[0]["agent"]["pos"]
        new_pos = changes[1]["agent"]["pos"]
        start_base_yaw = changes[0]["agent"]["base_yaw"]
        reldir_vec = rotation.DIRECTIONS[reldir]
        dir_vec = rotation.transform(reldir_vec, start_base_yaw, 0, inverted=True)
        dir_vec = np.array([dir_vec[0], dir_vec[2]], dtype="float32")
        tocheck_pos = np.around(old_pos + steps * dir_vec, 2)
        self.assertEqual(new_pos[0], tocheck_pos[0])
        self.assertEqual(new_pos[1], tocheck_pos[1])

    def setUp(self):
        super().setUp()

    def test_move_forward(self):
        d = MOVE_COMMANDS["move_forward"]
        changes = self.handle_logical_form(d)
        self.assert_move("FRONT", 1, changes)

    def test_move_right(self):
        d = GROUND_TRUTH_PARSES["go right 3 feet"]
        changes = self.handle_logical_form(d)
        self.assert_move("RIGHT", 3, changes)

    def test_move_left(self):
        d = GROUND_TRUTH_PARSES["go left 3 feet"]
        changes = self.handle_logical_form(d)
        self.assert_move("LEFT", 3, changes)

    def test_move_coordinates(self):
        d = MOVE_COMMANDS["move to -7 0 -8"]
        target = np.array((-7, -8))
        self.handle_logical_form(d)
        # check that agent moved
        self.assertLessEqual(np.linalg.norm(self.agent.pos - target), 1)

    def test_action_sequence_order(self):
        d = MOVE_COMMANDS["move to 3 0 2 then 7 0 7"]
        target = np.array((7, 7))
        print(d)
        self.handle_logical_form(d)
        print(self.agent.pos)
        self.assertLessEqual(np.linalg.norm(self.agent.pos - target), 1)

    def test_stop(self):
        # start moving
        target = np.array((-7, -8))
        d = MOVE_COMMANDS["move to -7 0 -8"]
        self.handle_logical_form(d, max_steps=5)

        # stop
        d = MOVE_COMMANDS["stop"]
        self.handle_logical_form(d)

        # assert that move did not complete
        self.assertGreater(np.linalg.norm(self.agent.pos - target), 1)


class MoveRefObjectsTest(BaseFakeAgentTestCase):
    def setUp(self):
        super().setUp()
        add_two_cubes(self)

    # do this one after we have players
    #    def test_move_here(self):
    #        d = MOVE_COMMANDS["move here"]
    #        self.handle_logical_form(d)
    #
    #        # check that agent moved
    #        self.assertLessEqual(euclid_dist(self.agent.pos, self.get_speaker_pos()), 1)

    def test_go_to_the_cube(self):
        d = MOVE_COMMANDS["go to the cube"]
        self.handle_logical_form(d)

        assert np.abs(self.agent.pos[1] - CUBE1[2]) < 1 or np.abs(self.agent.pos[1] - CUBE2[2]) < 1

    def test_between_cubes(self):
        d = MOVE_COMMANDS["go between the cubes"]
        self.handle_logical_form(d)
        print(self.agent.pos)
        assert self.agent.pos[1] > CUBE1[2] and self.agent.pos[1] < CUBE2[2]


class GetBringTest(BaseFakeAgentTestCase):
    def setUp(self):
        super().setUp()
        add_a_toy(self)

    def test_get_toy(self):
        d = MOVE_COMMANDS["get the toy"]
        self.handle_logical_form(d)

        d = MOVE_COMMANDS["move to -7 0 -8"]
        self.handle_logical_form(d)

        p = self.agent.world.objects[0]["pos"]
        ap = self.agent.pos

        assert (np.abs(ap[0] - p[0]) + np.abs(ap[1] - p[2])) < 1


class TurnTest(BaseFakeAgentTestCase):
    """Tests turn.

    Left turn is positive yaw, right turn is negative yaw.
    """

    def setUp(self):
        super().setUp()

    def test_turn_right(self):
        d = GROUND_TRUTH_PARSES["turn right 90 degrees"]
        changes = self.handle_logical_form(d)
        old_yaw = changes[0]["agent"]["base_yaw"]
        new_yaw = changes[1]["agent"]["base_yaw"]
        assert_turn_degree(old_yaw, new_yaw, -90)

    def test_turn_left(self):
        d = GROUND_TRUTH_PARSES["turn left 90 degrees"]
        changes = self.handle_logical_form(d)
        old_yaw = changes[0]["agent"]["base_yaw"]
        new_yaw = changes[1]["agent"]["base_yaw"]
        assert_turn_degree(old_yaw, new_yaw, 90)


class DanceTest(BaseFakeAgentTestCase):
    """Tests for dance."""

    def setUp(self):
        super().setUp()
        self.agent.add_object(CUBE1, tags=["cube"])
        self.agent.world.players = []

    def test_dance(self):
        # just checks for exceptions
        d = GROUND_TRUTH_PARSES["wave"]
        self.handle_logical_form(d)

    def test_look_at_cube(self):
        d = MOVE_COMMANDS["look at the cube"]
        self.handle_logical_form(d)
        camera_pos = [self.agent.pos[0], CAMERA_HEIGHT, self.agent.pos[1]]
        loc = self.agent.world.get_line_of_sight(
            camera_pos, self.agent.base_yaw + self.agent.pan, self.agent.pitch
        )
        self.assertLessEqual(
            np.linalg.norm(loc - np.array(self.agent.world.objects[0]["pos"])), 0.01
        )

        d = MOVE_COMMANDS["move to -7 0 -8"]
        self.handle_logical_form(d)

        d = MOVE_COMMANDS["look at the cube"]
        self.handle_logical_form(d)
        camera_pos = [self.agent.pos[0], CAMERA_HEIGHT, self.agent.pos[1]]
        loc = self.agent.world.get_line_of_sight(
            camera_pos, self.agent.base_yaw + self.agent.pan, self.agent.pitch
        )
        self.assertLessEqual(
            np.linalg.norm(loc - np.array(self.agent.world.objects[0]["pos"])), 0.01
        )


if __name__ == "__main__":
    unittest.main()
