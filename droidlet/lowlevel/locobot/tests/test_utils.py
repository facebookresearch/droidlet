"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from numpy.testing import assert_allclose
from numpy.linalg import norm
from numpy import array
import math
import unittest
import logging

from droidlet.lowlevel.robot_mover_utils import (
    get_move_target_for_point,
    xyz_canonical_coords_to_pyrobot_coords,
    xyz_pyrobot_to_canonical_coords,
    pyrobot_to_canonical_frame,
)


def assert_distance_moved(pos1, pos2, movement_vector):
    act_dist = norm(array(pos1)[:2] - array(pos2)[:2])
    goal_dist = norm(array(movement_vector)[:2])
    assert_allclose(act_dist, goal_dist, rtol=1e-3)


def assert_turn_degree(initial_yaw, final_yaw, turn_degree):
    """Asserts the difference in final and initial yaws is degree."""
    logging.info(
        "{}, {}, {}".format(math.degrees(initial_yaw), math.degrees(final_yaw), turn_degree)
    )
    initial_d = math.degrees(initial_yaw) % 360
    final_d = math.degrees(final_yaw) % 360
    expect_fd = (initial_d + turn_degree) % 360
    # to make dist(0, 359.9) = dist(0, 0.1), convert angle to 2D location based on unit circle and then compare location
    final_loc = [math.cos(math.radians(final_d)), math.sin(math.radians(final_d))]
    expect_loc = [math.cos(math.radians(expect_fd)), math.sin(math.radians(expect_fd))]
    assert_allclose(final_loc, expect_loc, atol=2e-7)


class UtilsTest(unittest.TestCase):
    def test_assert_turn_degree(self):
        self.assertRaises(AssertionError, assert_turn_degree, 0, math.radians(10), 90)
        self.assertRaises(AssertionError, assert_turn_degree, 0, 0, 90)
        self.assertRaises(AssertionError, assert_turn_degree, 0, 0, -90)
        self.assertRaises(AssertionError, assert_turn_degree, 0, 0, 180)
        assert_turn_degree(0, 0, 360)
        assert_turn_degree(0, math.radians(90), 90)
        assert_turn_degree(math.radians(90), math.radians(180), 90)
        assert_turn_degree(math.radians(-45), math.radians(45), 90)
        assert_turn_degree(math.radians(45), math.radians(-45), -90)
        assert_turn_degree(math.radians(-45), math.radians(-45), 360)


class LocoboMoverUtilsTest(unittest.TestCase):
    """
    Coordinate transform related tests https://github.com/facebookresearch/droidlet/blob/main/locobot/coordinates.MD
    """

    def test_pyrobot_to_canonical_to_pyrobot(self):
        pt_r = (1, 2, 3)
        pt_c = xyz_pyrobot_to_canonical_coords(pt_r)
        assert_allclose(pt_c, (-2, 3, 1))
        assert_allclose(xyz_canonical_coords_to_pyrobot_coords(pt_c), pt_r)

    def test_canonical_to_pyrobot_to_canonical(self):
        pt_c = (1, 2, 3)
        pt_r = xyz_canonical_coords_to_pyrobot_coords(pt_c)
        assert_allclose(pt_r, (3, -1, 2))
        assert_allclose(xyz_pyrobot_to_canonical_coords(pt_r), pt_c)

    def test_get_move_target_for_point(self):
        base_pos = (0, 0, 0)
        # test each quadrant

        # define a dictionary that maps point target to move targets if eps is 1 (ie we want to move to with 1)
        # of the x, z and coordinates.
        target_move_dict_1 = {
            (2, 0, 3): (1, 2),  # (x,y,z) : (x,z)
            (-2, 0, 3): (-1, 2),
            (-2, 0, -3): (-1, -2),
            (2, 0, -3): (1, -2),
        }

        for pt_target, mv_target in target_move_dict_1.items():
            act_mv = get_move_target_for_point(base_pos, pt_target, eps=1)
            assert_allclose(act_mv[:2], mv_target)

        # check for eps 4
        target_move_dict_4 = {
            (2, 0, 3): (-2, -1),
            (-2, 0, 3): (2, -1),
            (-2, 0, -3): (2, 1),
            (2, 0, -3): (-2, 1),
        }

        for pt_target, mv_target in target_move_dict_4.items():
            act_mv = get_move_target_for_point(base_pos, pt_target, eps=4)
            assert_allclose(act_mv[:2], mv_target)


if __name__ == "__main__":
    unittest.main()
