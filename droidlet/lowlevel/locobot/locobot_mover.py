"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import os
import sys
import math
import copy
import time
import logging
from collections.abc import Iterable
from prettytable import PrettyTable
import Pyro4
import numpy as np

if "/opt/ros/kinetic/lib/python2.7/dist-packages" in sys.path:
    sys.path.remove("/opt/ros/kinetic/lib/python2.7/dist-packages")

from droidlet.shared_data_structs import ErrorWithResponse
from agents.argument_parser import ArgumentParser
from droidlet.shared_data_structs import RGBDepth

from ..robot_mover_utils import (
    get_camera_angles,
    angle_diff,
    MAX_PAN_RAD,
    CAMERA_HEIGHT,
    ARM_HEIGHT,
    transform_pose,
    base_canonical_coords_to_pyrobot_coords,
    xyz_pyrobot_to_canonical_coords,
)
from tenacity import retry, stop_after_attempt, wait_fixed

Pyro4.config.SERIALIZER = "pickle"
Pyro4.config.SERIALIZERS_ACCEPTED.add("pickle")


@retry(reraise=True, stop=stop_after_attempt(5), wait=wait_fixed(0.5))
def safe_call(f, *args):
    try:
        return f(*args)
    except Pyro4.errors.ConnectionClosedError as e:
        msg = "{} - {}".format(f._RemoteMethod__name, e)
        raise ErrorWithResponse(msg)


class LoCoBotMover:
    """Implements methods that call the physical interfaces of the Locobot.

    Arguments:
        ip (string): IP of the Locobot.
        backend (string): backend where the Locobot lives, either "habitat" or "locobot"
    """

    def __init__(self, ip=None, backend="locobot"):
        self.bot = Pyro4.Proxy("PYRONAME:remotelocobot@" + ip)
        self.close_loop = False if backend == "habitat" else True
        self.curr_look_dir = np.array([0, 0, 1])  # initial look dir is along the z-axis

        intrinsic_mat = safe_call(self.bot.get_intrinsics)
        intrinsic_mat_inv = np.linalg.inv(intrinsic_mat)
        img_resolution = safe_call(self.bot.get_img_resolution)
        img_pixs = np.mgrid[0 : img_resolution[0] : 1, 0 : img_resolution[1] : 1]
        img_pixs = img_pixs.reshape(2, -1)
        img_pixs[[0, 1], :] = img_pixs[[1, 0], :]
        uv_one = np.concatenate((img_pixs, np.ones((1, img_pixs.shape[1]))))
        self.uv_one_in_cam = np.dot(intrinsic_mat_inv, uv_one)
        self.backend = backend

    def check(self):
        """
        Sanity checks all the mover interfaces.

        Checks move by moving the locobot around in a square and reporting L1 drift and total time taken
            for the three movement modes available to the locobot - using PyRobot slam (vslam),
            using Droidlet slam (dslam) and without using any slam (default)
        Checks look and point by poiting and looking at the same target.
        """
        self.reset_camera()
        table = PrettyTable(["Command", "L1 Drift (meters)", "Time (sec)"])
        sq_table = PrettyTable(["Mode", "Total L1 drift (meters)", "Total time (sec)"])

        def l1_drift(a, b):
            return round(abs(a[0] - b[0]) + abs(a[1] - b[1]), ndigits=3)

        def execute_move(init_pos, dest_pos, cmd_text, use_map=False, use_dslam=False):
            logging.info("Executing {} ... ".format(cmd_text))
            start = time.time()
            self.move_absolute([dest_pos], use_map=use_map, use_dslam=use_dslam)
            end = time.time()
            tt = round((end - start), ndigits=3)
            pos_after = self.get_base_pos_in_canonical_coords()
            drift = l1_drift(pos_after, dest_pos)
            logging.info("Finished Executing. \nDrift: {} Time taken: {}".format(drift, tt))
            table.add_row([cmd_text, drift, tt])
            return drift, tt

        def move_in_a_square(magic_text, side=0.3, use_vslam=False, use_dslam=False):
            """
            Moves the locobot in a square starting from the bottom right - goes left, forward, right, back.

            Args:
                magic_text (str): unique text to differentiate each scenario
                side (float): side of the square

            Returns:
                total L1 drift, total time taken to move around the square.
            """
            pos = self.get_base_pos_in_canonical_coords()
            logging.info("Initial agent pos {}".format(pos))
            dl, tl = execute_move(
                pos,
                [pos[0] - side, pos[1], pos[2]],
                "Move Left " + magic_text,
                use_map=use_vslam,
                use_dslam=use_dslam,
            )
            df, tf = execute_move(
                pos,
                [pos[0] - side, pos[1] + side, pos[2]],
                "Move Forward " + magic_text,
                use_map=use_vslam,
                use_dslam=use_dslam,
            )
            dr, tr = execute_move(
                pos,
                [pos[0], pos[1] + side, pos[2]],
                "Move Right " + magic_text,
                use_map=use_vslam,
                use_dslam=use_dslam,
            )
            db, tb = execute_move(
                pos,
                [pos[0], pos[1], pos[2]],
                "Move Backward " + magic_text,
                use_map=use_vslam,
                use_dslam=use_dslam,
            )
            return dl + df + dr + db, tl + tf + tr + tb

        # move in a square of side 0.3 starting at current base pos
        d, t = move_in_a_square("default", side=0.3, use_vslam=False, use_dslam=False)
        sq_table.add_row(["default", d, t])

        d, t = move_in_a_square("use_vslam", side=0.3, use_vslam=True, use_dslam=False)
        sq_table.add_row(["use_vslam", d, t])

        d, t = move_in_a_square("use_dslam", side=0.3, use_vslam=False, use_dslam=True)
        sq_table.add_row(["use_dslam", d, t])

        print(table)
        print(sq_table)

        # Check that look & point are at the same target
        logging.info("Visually check that look and point are at the same target")
        pos = self.get_base_pos_in_canonical_coords()
        look_pt_target = [pos[0] + 0.5, 1, pos[1] + 1]

        # look
        self.look_at(look_pt_target, 0, 0)
        logging.info("Completed Look at.")

        # point
        self.point_at(look_pt_target)
        logging.info("Completed Point.")

    # TODO/FIXME!  instead of just True/False, return diagnostic messages
    # so e.g. if a grip attempt fails, the task is finished, but the status is a failure
    def bot_step(self):
        try:
            f = self.bot.command_finished()
        except:
            # do better here?
            f = True
        return f

    def get_pan(self):
        """get yaw in radians."""
        return self.bot.get_pan()

    def get_tilt(self):
        """get pitch in radians."""
        return self.bot.get_tilt()

    def reset_camera(self):
        """reset the camera to 0 pan and tilt."""
        return self.bot.reset()

    def move_relative(self, xyt_positions, use_dslam=True):
        """Command to execute a relative move.

        Args:
            xyt_positions: a list of relative (x,y,yaw) positions for the bot to execute.
            x,y,yaw are in the pyrobot's coordinates.
        """
        if not isinstance(next(iter(xyt_positions)), Iterable):
            # single xyt position given
            xyt_positions = [xyt_positions]
        for xyt in xyt_positions:
            self.bot.go_to_relative(xyt, close_loop=self.close_loop, use_dslam=use_dslam)
            while not self.bot.command_finished():
                print(self.bot.get_base_state("odom"))

    def move_absolute(self, xyt_positions, use_map=False, use_dslam=True):
        """Command to execute a move to an absolute position.

        It receives positions in canonical world coordinates and converts them to pyrobot's coordinates
        before calling the bot APIs.

        Args:
            xyt_positions: a list of (x_c,y_c,yaw) positions for the bot to move to.
            (x_c,y_c,yaw) are in the canonical world coordinates.
        """
        if not isinstance(next(iter(xyt_positions)), Iterable):
            # single xyt position given
            xyt_positions = [xyt_positions]
        for xyt in xyt_positions:
            logging.info("Move absolute in canonical coordinates {}".format(xyt))
            self.bot.go_to_absolute(
                base_canonical_coords_to_pyrobot_coords(xyt),
                close_loop=self.close_loop,
                use_map=use_map,
                use_dslam=use_dslam,
            )
            start_base_state = self.get_base_pos_in_canonical_coords()
            while not self.bot.command_finished():
                print(self.get_base_pos_in_canonical_coords())

            end_base_state = self.get_base_pos_in_canonical_coords()
            logging.info(
                "start {}, end {}, diff {}".format(
                    start_base_state,
                    end_base_state,
                    [b - a for a, b in zip(start_base_state, end_base_state)],
                )
            )
        return "finished"

    def look_at(self, obj_pos, yaw_deg, pitch_deg):
        """Executes "look at" by setting the pan, tilt of the camera or turning the base if required.

        Uses both the base state and object coordinates in canonical world coordinates to calculate
        expected yaw and pitch.

        Args:
            obj_pos (list): object coordinates as saved in memory.
            yaw_deg (float): yaw in degrees
            pitch_deg (float): pitch in degrees

        Returns:
            string "finished"
        """
        pan_rad, tilt_rad = 0.0, 0.0
        old_pan = self.get_pan()
        old_tilt = self.get_tilt()
        pos = self.get_base_pos_in_canonical_coords()
        logging.info(f"Current Locobot state (x, z, yaw): {pos}")
        if yaw_deg:
            pan_rad = old_pan - float(yaw_deg) * np.pi / 180
        if pitch_deg:
            tilt_rad = old_tilt - float(pitch_deg) * np.pi / 180
        if obj_pos is not None:
            logging.info(f"looking at x,y,z: {obj_pos}")
            pan_rad, tilt_rad = get_camera_angles([pos[0], CAMERA_HEIGHT, pos[1]], obj_pos)
            logging.info(f"Returned new pan and tilt angles (radians): ({pan_rad}, {tilt_rad})")

        # FIXME!!! more async; move head and body at the same time
        head_res = angle_diff(pos[2], pan_rad)
        if np.abs(head_res) > MAX_PAN_RAD:
            dyaw = np.sign(head_res) * (np.abs(head_res) - MAX_PAN_RAD)
            self.turn(dyaw)
            pan_rad = np.sign(head_res) * MAX_PAN_RAD
        else:
            pan_rad = head_res
        logging.info(f"Camera new pan and tilt angles (radians): ({pan_rad}, {tilt_rad})")
        self.bot.set_pan_tilt(pan_rad, np.clip(tilt_rad, tilt_rad, 0.9))
        logging.debug(f"locobot pan and tilt now: ({self.bot.get_camera_state()})")

        return "finished"

    def point_at(self, target_pos):
        """Executes pointing the arm at the specified target pos.

        Args:
            target_pos ([x,y,z]): canonical coordinates to point to.

        Returns:
            string "finished"
        """
        pos = self.get_base_pos_in_canonical_coords()
        yaw_rad, pitch_rad = get_camera_angles([pos[0], ARM_HEIGHT, pos[1]], target_pos)
        states = [
            [yaw_rad, 0.0, pitch_rad, 0.0, 0.0],
            [yaw_rad, 0.0, pitch_rad, -0.2, 0.0],
            [0.0, -math.pi / 4.0, math.pi / 2.0, 0.0, 0.0],  # reset joint position
        ]
        for state in states:
            self.bot.set_joint_positions(state, plan=False)
            while not self.bot.command_finished():
                pass
        return "finished"

    def get_base_pos_in_canonical_coords(self):
        """get the current Locobot position in the canonical coordinate system
        instead of the Locobot's global coordinates as stated in the Locobot
        documentation: https://www.pyrobot.org/docs/navigation.

        the standard coordinate systems:
          Camera looks at (0, 0, 1),
          its right direction is (1, 0, 0) and
          its up-direction is (0, 1, 0)

         return:
         (x, z, yaw) of the Locobot base in standard coordinates
        """

        x_global, y_global, yaw = safe_call(self.bot.get_base_state, "odom")
        x_standard = -y_global
        z_standard = x_global
        return np.array([x_standard, z_standard, yaw])

    def get_base_pos(self):
        """Return Locobot (x, y, yaw) in the robot base coordinates as
        illustrated in the docs:

        https://www.pyrobot.org/docs/navigation
        """
        return self.bot.get_base_state("odom")

    def get_rgb_depth(self):
        """Fetches rgb, depth and pointcloud in pyrobot world coordinates.

        Returns:
            an RGBDepth object
        """
        rgb, depth, rot, trans = self.bot.get_pcd_data()
        depth = depth.astype(np.float32)
        d = copy.deepcopy(depth)
        depth /= 1000.0
        depth = depth.reshape(-1)
        pts_in_cam = np.multiply(self.uv_one_in_cam, depth)
        pts_in_cam = np.concatenate((pts_in_cam, np.ones((1, pts_in_cam.shape[1]))), axis=0)
        pts = pts_in_cam[:3, :].T
        pts = np.dot(pts, rot.T)
        pts = pts + trans.reshape(-1)
        if self.backend == "habitat":
            ros_to_habitat_frame = np.array([[0.0, -1.0, 0.0], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0]])
            pts = ros_to_habitat_frame.T @ pts.T
            pts = pts.T
        pts = transform_pose(pts, self.bot.get_base_state("odom"))
        logging.info("Fetched all camera sensor input.")
        return RGBDepth(rgb, d, pts)

    def dance(self):
        self.bot.dance()

    def turn(self, yaw):
        """turns the bot by the yaw specified.

        Args:
            yaw: the yaw to execute in degree.
        """
        turn_rad = yaw * math.pi / 180
        self.bot.go_to_relative([0, 0, turn_rad], close_loop=self.close_loop)

    def grab_nearby_object(self, bounding_box=[(240, 480), (100, 540)]):
        """
        :param bounding_box: region in image to search for grasp
        """
        return self.bot.grasp(bounding_box)

    def is_object_in_gripper(self):
        return self.bot.get_gripper_state() == 2

    def explore(self):
        return self.bot.explore()

    def drop(self):
        return self.bot.open_gripper()

    def get_obstacles_in_canonical_coords(self):
        """get the positions of obtacles position in the canonical coordinate system
        instead of the Locobot's global coordinates as stated in the Locobot
        documentation: https://www.pyrobot.org/docs/navigation or
        https://github.com/facebookresearch/pyrobot/blob/master/docs/website/docs/ex_navigation.md

        the standard coordinate systems:
          Camera looks at (0, 0, 1),
         its right direction is (1, 0, 0) and
         its up-direction is (0, 1, 0)

         return:
         list[(x, z)] of the obstacle location in standard coordinates
        """
        cordinates_in_robot_frame = self.bot.get_map()
        cordinates_in_standard_frame = [
            xyz_pyrobot_to_canonical_coords(list(c) + [0.0]) for c in cordinates_in_robot_frame
        ]
        cordinates_in_standard_frame = [(c[0], c[2]) for c in cordinates_in_standard_frame]
        return cordinates_in_standard_frame


if __name__ == "__main__":
    base_path = os.path.dirname(__file__)
    parser = ArgumentParser("Locobot", base_path)
    opts = parser.parse()
    mover = LoCoBotMover(ip=opts.ip, backend=opts.backend)
    if opts.check_controller:
        mover.check()
