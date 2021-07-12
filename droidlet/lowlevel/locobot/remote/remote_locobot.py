"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
# python -m Pyro4.naming -n <MYIP>
import Pyro4
from pyrobot import Robot
import numpy as np
from scipy.spatial.transform import Rotation
import logging
import os
import json
import skfmm
import skimage
from pyrobot.locobot.camera import DepthImgProcessor
from slam_pkg.slam import Slam

Pyro4.config.SERIALIZERS_ACCEPTED.add("pickle")
Pyro4.config.ITER_STREAMING = True


@Pyro4.expose
class RemoteLocobot(object):
    """PyRobot interface for the Locobot.

    Args:
        backend (string): the backend for the Locobot ("habitat" for the locobot in Habitat, and "locobot" for the physical LocoBot)
        (default: locobot)
        backend_config (dict): the backend config used for connecting to Habitat (default: None)
    """

    def __init__(self, backend="locobot", backend_config=None, noisy=False):
        if backend == "locobot":
            base_config_dict = {"base_controller": "proportional"}
            arm_config_dict = dict(moveit_planner="ESTkConfigDefault")
            self._robot = Robot(
                backend,
                use_base=True,
                use_arm=True,
                use_camera=True,
                base_config=base_config_dict,
                arm_config=arm_config_dict,
            )

            self._dip = DepthImgProcessor()

            from grasp_samplers.grasp import Grasper

        elif backend == "habitat":
            if backend_config["physics_config"] == "DEFAULT":
                assets_path = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "../tests/test_assets")
                )
                backend_config["physics_config"] = os.path.join(
                    assets_path, "default.phys_scene_config.json"
                )
            backend_config["noisy"] = noisy
            print("backend_config", backend_config)
            self.backend_config = backend_config
            # we do it this way to have the ability to restart from the client at arbitrary times
            self.restart_habitat()
        else:
            raise RuntimeError("Unknown backend", backend)

        # check skfmm, skimage in installed, its necessary for slam
        self._slam = Slam(self._robot, backend)
        self._slam_step_size = 25  # step size in cm
        self._done = True
        self.backend = backend

    def restart_habitat(self):
        if hasattr(self, "_robot"):
            del self._robot
        backend_config = self.backend_config
        self._robot = Robot("habitat", common_config=backend_config)
        # todo: a bad package seems to override python logging after the line above is run.
        # So, all `logging.warn` and `logging.info` calls are failing to route
        # to STDOUT/STDERR after this.
        from habitat_utils import reconfigure_scene

        # adds objects to the scene, doing scene-specific configurations
        reconfigure_scene(self, backend_config["scene_path"])
        from pyrobot.locobot.camera import DepthImgProcessor

        if hasattr(self, "_dip"):
            del self._dip
        self._dip = DepthImgProcessor(cfg_filename="realsense_habitat.yaml")

    def test_connection(self):
        print("Connected!!")  # should print on server terminal
        return "Connected!"  # should print on client terminal

    def get_img_resolution(self):
        """return height and width"""
        if self.backend == "locobot":
            return (
                self._robot.camera.depth_cam.cfg_data["Camera.height"],
                self._robot.camera.depth_cam.cfg_data["Camera.width"],
            )
        elif self.backend == "habitat":
            return (512, 512)
        else:
            return None

    def get_pcd_data(self):
        """Gets all the data to calculate the point cloud for a given rgb, depth frame."""
        rgb, depth = self._robot.camera.get_rgb_depth()
        depth *= 1000  # convert to mm
        # cap anything more than np.power(2,16)~ 65 meter
        depth[depth > np.power(2, 16) - 1] = np.power(2, 16) - 1
        depth = depth.astype(np.uint16)
        if self.backend == "locobot":
            trans, rot, T = self._robot.camera.get_link_transform(
                self._robot.camera.cam_cf, self._robot.camera.base_f
            )
            base2cam_trans = np.array(trans).reshape(-1, 1)
            base2cam_rot = np.array(rot)
            return rgb, depth, base2cam_rot, base2cam_trans
        elif self.backend == "habitat":
            cur_state = self._robot.camera.agent.get_state()
            cur_sensor_state = cur_state.sensor_states["rgb"]
            initial_rotation = cur_state.rotation
            rot_init_rotation = self._robot.camera._rot_matrix(initial_rotation)
            relative_position = cur_sensor_state.position - cur_state.position
            relative_position = rot_init_rotation.T @ relative_position
            cur_rotation = self._robot.camera._rot_matrix(cur_sensor_state.rotation)
            cur_rotation = rot_init_rotation.T @ cur_rotation
            return rgb, depth, cur_rotation, -relative_position
        return None

    # Navigation wrapper
    @Pyro4.oneway
    def go_home(self, use_dslam=False):
        """Moves the robot base to origin point: x, y, yaw 0, 0, 0."""
        if self._done:
            self._done = False
            if use_dslam:
                self._slam.set_absolute_goal_in_robot_frame([0.0, 0.0, 0.0])
            else:
                self._robot.base.go_to_absolute([0, 0, 0])
            self._done = True

    def go_to_absolute(
        self,
        xyt_position,
        use_map=False,
        close_loop=True,
        smooth=False,
        use_dslam=False,
    ):
        """Moves the robot base to given goal state in the world frame.

        :param xyt_position: The goal state of the form (x,y,yaw)
                             in the world (map) frame.
        :param use_map: When set to "True", ensures that controller is
                        using only free space on the map to move the robot.
        :param close_loop: When set to "True", ensures that controller
                           is operating in open loop by taking
                           account of odometry.
        :param smooth: When set to "True", ensures that the motion
                       leading to the goal is a smooth one.
        :param use_dslam: When set to "True", the robot uses slam for
                          the navigation.

        :type xyt_position: list or np.ndarray
        :type use_map: bool
        :type close_loop: bool
        :type smooth: bool
        """
        if self._done:
            self._done = False
            if use_dslam:
                self._slam.set_absolute_goal_in_robot_frame(xyt_position)
            else:
                self._robot.base.go_to_absolute(
                    xyt_position, use_map=use_map, close_loop=close_loop, smooth=smooth
                )
            self._done = True

    def go_to_relative(
        self,
        xyt_position,
        use_map=False,
        close_loop=True,
        smooth=False,
        use_dslam=False,
    ):
        """Moves the robot base to the given goal state relative to its current
        pose.

        :param xyt_position: The  relative goal state of the form (x,y,yaw)
        :param use_map: When set to "True", ensures that controller is
                        using only free space on the map to move the robot.
        :param close_loop: When set to "True", ensures that controller is
                           operating in open loop by taking
                           account of odometry.
        :param smooth: When set to "True", ensures that the
                       motion leading to the goal is a smooth one.
        :param use_dslam: When set to "True", the robot uses slam for
                          the navigation.

        :type xyt_position: list or np.ndarray
        :type use_map: bool
        :type close_loop: bool
        :type smooth: bool
        """
        if self._done:
            self._done = False
            if use_dslam:
                self._slam.set_relative_goal_in_robot_frame(xyt_position)
            else:
                self._robot.base.go_to_relative(
                    xyt_position, use_map=use_map, close_loop=close_loop, smooth=smooth
                )
            self._done = True

    @Pyro4.oneway
    def stop(self):
        """stops robot base movement."""
        self._robot.base.stop()

    def get_base_state(self, state_type):
        """Returns the  base pose of the robot in the (x,y, yaw) format as
        computed either from Wheel encoder readings or Visual-SLAM.

        :param state_type: Requested state type. Ex: Odom, SLAM, etc

        :type state_type: string

        :return: pose of the form [x, y, yaw]
        :rtype: list
        """
        return self._robot.base.get_state(state_type)

    # Manipulation wrapper

    @Pyro4.oneway
    def set_joint_positions(self, target_joint, plan=False):
        """Sets the desired joint angles for all arm joints.

        :param target_joint: list of length #of joints(5 for locobot), angles in radians,
                             order-> base_join index 0, wrist joint index -1
        :param plan: whether to use moveit to plan a path. Without planning,
                     there is no collision checking and each joint will
                     move to its target joint position directly.

        :type target_joint: list
        :type plan: bool
        """
        if self._done:
            self._done = False
            target_joint = np.array(target_joint)
            self._robot.arm.set_joint_positions(target_joint, plan=plan)
            self._done = True

    @Pyro4.oneway
    def set_joint_velocities(self, target_vels):
        """Sets the desired joint velocities for all arm joints.

        :param target_vels: target joint velocities, list of length #of joints(5 for locobot)
                            velocity in  radians/sec
                            order-> base_join index 0, wrist joint index -1
        :type target_vels: list
        """
        if self._done:
            self._done = False
            target_vels = np.array(target_vels)
            self._robot.arm.set_joint_velocities(target_vels)
            self._done = True

    @Pyro4.oneway
    def set_ee_pose(self, position, orientation, plan=False):
        """Commands robot arm to desired end-effector pose (w.r.t.
        'ARM_BASE_FRAME'). Computes IK solution in joint space and calls
        set_joint_positions.

        :param position: position of the end effector in metric (shape: :math:`[3,]`)
        :param orientation: orientation of the end effector
                            (can be rotation matrix, euler angles (yaw,
                            pitch, roll), or quaternion)
                            (shape: :math:`[3, 3]`, :math:`[3,]`
                            or :math:`[4,]`)
                            The convention of the Euler angles here
                            is z-y'-x' (intrinsic rotations),
                            which is one type of Tait-Bryan angles.
        :param plan: use moveit the plan a path to move to the desired pose

        :type position: list or np.ndarray
        :type orientation: list or np.ndarray
        :type plan: bool
        """
        if self._done:
            self._done = False
            position = np.array(position)
            orientation = np.array(orientation)
            self._robot.arm.set_ee_pose(position, orientation, plan=plan)
            self._done = True

    @Pyro4.oneway
    def move_ee_xyz(self, displacement, eef_step=0.005, plan=False):
        """Keep the current orientation of arm fixed, move the end effector of
        in {xyz} directions.

        :param displacement: (delta_x, delta_y, delta_z) in metric unit
        :param eef_step: resolution (m) of the interpolation
                         on the cartesian path
        :param plan: use moveit the plan a path to move to the
                     desired pose. If False,
                     it will do linear interpolation along the path,
                     and simply use IK solver to find the
                     sequence of desired joint positions and
                     then call `set_joint_positions`

        :type displacement: list or np.ndarray
        :type eef_step: float
        :type plan: bool
        """
        if self._done:
            self._done = False
            displacement = np.array(displacement)
            self._robot.arm.move_ee_xyz(displacement, eef_step, plan=plan)
            self._done = True

    # Gripper wrapper
    @Pyro4.oneway
    def open_gripper(self):
        """Commands gripper to open fully."""
        if self._done:
            self._done = False
            self._robot.gripper.open()
            self._done = True

    @Pyro4.oneway
    def close_gripper(self):
        """Commands gripper to close fully."""
        if self._done:
            self._done = False
            self._robot.gripper.close()
            self._done = True

    def get_gripper_state(self):
        """Return the gripper state.

        :return: state
                 state = -1: unknown gripper state
                 state = 0: gripper is fully open
                 state = 1: gripper is closing
                 state = 2: there is an object in the gripper
                 state = 3: gripper is fully closed
        :rtype: int
        """
        return self._robot.gripper.get_gripper_state()

    def get_end_eff_pose(self):
        """
        Return the end effector pose w.r.t 'ARM_BASE_FRAME'
        :return:tuple (trans, rot_mat, quat)

                trans: translational vector in metric unit (shape: :math:`[3, 1]`)

                rot_mat: rotational matrix (shape: :math:`[3, 3]`)

                quat: rotational matrix in the form of quaternion (shape: :math:`[4,]`)

        :rtype: tuple (list, list, list)
        """
        pos, rotmat, quat = self._robot.arm.pose_ee
        return pos.flatten().tolist(), rotmat.tolist(), quat.tolist()

    def get_joint_positions(self):
        """Return arm joint angles order-> base_join index 0, wrist joint index
        -1.

        :return: joint_angles in radians
        :rtype: list
        """
        return self._robot.arm.get_joint_angles().tolist()

    def get_joint_velocities(self):
        """Return the joint velocity order-> base_join index 0, wrist joint
        index -1.

        :return: joint_angles in rad/sec
        :rtype: list
        """
        return self._robot.arm.get_joint_velocities().tolist()

    # Common wrapper
    def command_finished(self):
        """Returns whether previous executed command finished execution.

        return: command execution state [True for finished execution, False for still executing]
        rtype: bool
        """
        return self._done

    # Camera wrapper
    def get_depth(self):
        """Returns the depth image perceived by the camera.

        :return: depth image in meters, dtype-> float32
        :rtype: np.ndarray or None
        """
        depth = self._robot.camera.get_depth()
        if depth is not None:
            return depth
        return None

    def get_depth_bytes(self):
        """Returns the depth image perceived by the camera.

        :return: depth image in meters, dtype-> bytes
        :rtype: np.ndarray or None
        """
        depth = self._robot.camera.get_depth().astype(np.int64)
        if depth is not None:
            return depth.tobytes()
        return None

    def get_intrinsics(self):
        """Returns the intrinsic matrix of the camera.

        :return: the intrinsic matrix (shape: :math:`[3, 3]`)
        :rtype: list
        """
        intrinsics = self._robot.camera.get_intrinsics()
        if intrinsics is not None:
            return intrinsics.tolist()
        return None

    def get_rgb(self):
        """Returns the RGB image perceived by the camera.

        :return: image in the RGB, [h,w,c] format, dtype->uint8
        :rtype: np.ndarray or None
        """
        rgb = self._robot.camera.get_rgb()
        if rgb is not None:
            return rgb
        return None

    def get_rgbd_segm(self):
        """Returns the RGB image, depth, instance segmentation map."""
        rgb, d, segm = self._robot.camera.get_rgb_depth_segm()
        if rgb is not None:
            return rgb, d, segm
        return None

    def get_rgb_bytes(self):
        """Returns the RGB image perceived by the camera.

        :return: image in the RGB, [h,w,c] format, dtype->bytes
        :rtype: np.ndarray or None
        """
        rgb = self._robot.camera.get_rgb().astype(np.int64)
        if rgb is not None:
            return rgb.tobytes()
        return None

    def transform_pose(self, XYZ, current_pose):
        """
        Transforms the point cloud into geocentric frame to account for
        camera position

        Args:
            XYZ                     : ...x3
            current_pose            : camera position (x, y, theta (radians))
        Returns:
            XYZ : ...x3
        """
        R = Rotation.from_euler("Z", current_pose[2]).as_matrix()
        XYZ = np.matmul(XYZ.reshape(-1, 3), R.T).reshape((-1, 3))
        XYZ[:, 0] = XYZ[:, 0] + current_pose[0]
        XYZ[:, 1] = XYZ[:, 1] + current_pose[1]
        return XYZ

    def get_current_pcd(self, in_cam=False, in_global=False):
        """Return the point cloud at current time step.

        :param in_cam: return points in camera frame,
                       otherwise, return points in base frame

        :type in_cam: bool

        :returns: tuple (pts, colors)

                  pts: point coordinates (shape: :math:`[N, 3]`) in metric unit

                  colors: rgb values (shape: :math:`[N, 3]`)
        :rtype: tuple(list, list)
        """
        pts, colors = self._robot.camera.get_current_pcd(in_cam=in_cam)

        if in_global:
            pts = self.transform_pose(pts, self._robot.base.get_state("odom"))
        return pts, colors

    def pix_to_3dpt(self, rs, cs, in_cam=False):
        """Get the 3D points of the pixels in RGB images in metric unit.

        :param rs: rows of interest in the RGB image.
                   It can be a list or 1D numpy array
                   which contains the row indices.
        :param cs: columns of interest in the RGB image.
                   It can be a list or 1D numpy array
                   which contains the column indices.
        :param in_cam: return points in camera frame,
                       otherwise, return points in base frame

        :type rs: list or np.ndarray
        :type cs: list or np.ndarray
        :type in_cam: bool

        :returns: tuple (pts, colors)

                  pts: point coordinates in metric unit
                  (shape: :math:`[N, 3]`)

                  colors: rgb values
                  (shape: :math:`[N, 3]`)

        :rtype: tuple(list, list)
        """
        pts, colors = self._robot.camera.pix_to_3dpt(rs, cs, in_cam=in_cam)
        return pts.tolist(), colors.tolist()

    def dip_pix_to_3dpt(self):
        """Return the point cloud at current time step in robot base frame.

        :returns: point coordinates (shape: :math:`[N, 3]`) in metric unit
        :rtype: list
        """
        logging.info("dip_pix_to_3dpt")
        depth = self._robot.camera.get_depth()
        h = depth.shape[0]
        w = depth.shape[1]

        xs = np.repeat(np.arange(h), w).ravel()
        ys = np.repeat(np.arange(w)[None, :], h, axis=0).ravel()

        pts = self.pix_to_3dpt(xs, ys)
        pts = np.around(pts, decimals=2)
        logging.info("exiting pix_to_3dpt")
        return pts

    def get_transform(self, src_frame, dst_frame):
        """Return the transform from the src_frame to dest_frame.

        :param src_frame: source frame
        :param dst_frame: destination frame

        :type src_frame: str
        :type dst_frame: str

        :return:tuple (trans, rot_mat, quat )
                trans: translational vector (shape: :math:`[3, 1]`)
                rot_mat: rotational matrix (shape: :math:`[3, 3]`)
                quat: rotational matrix in the form of quaternion (shape: :math:`[4,]`)

        :rtype: tuple(np.ndarray, np.ndarray, np.ndarray)
        """
        return self._robot.arm.get_transform(src_frame, dst_frame)

    # Camera pan wrapper
    def get_pan(self):
        """Return the current pan joint angle of the robot camera.

        :return:Pan joint angle in radian
        :rtype: float
        """
        return self._robot.camera.get_pan()

    def get_camera_state(self):
        """Return the current pan and tilt joint angles of the robot camera in
        radian.

        :return: A list the form [pan angle, tilt angle]
        :rtype: list
        """
        return self._robot.camera.get_state()

    def get_tilt(self):
        """Return the current tilt joint angle of the robot camera in radian.

        :return:tilt joint angle
        :rtype: float
        """
        return self._robot.camera.get_tilt()

    @Pyro4.oneway
    def reset(self):
        """This function resets the pan and tilt joints of robot camera by
        actuating them to their home configuration [0.0, 0.0]."""
        if self._done:
            self._done = False
            self._robot.camera.reset()
            self._done = True

    @Pyro4.oneway
    def set_pan(self, pan, wait=True):
        """Sets the pan joint angle of robot camera to the specified value.

        :param pan: value to be set for pan joint in radian
        :param wait: wait until the pan angle is set to
                     the target angle.

        :type pan: float
        :type wait: bool
        """
        if self._done:
            self._done = False
            self._robot.camera.set_pan(pan, wait=wait)
            self._done = True

    @Pyro4.oneway
    def set_pan_tilt(self, pan, tilt, wait=True):
        """Sets both the pan and tilt joint angles of the robot camera  to the
        specified values.

        :param pan: value to be set for pan joint in radian
        :param tilt: value to be set for the tilt joint in radian
        :param wait: wait until the pan and tilt angles are set to
                     the target angles.

        :type pan: float
        :type tilt: float
        :type wait: bool
        """
        if self._done:
            self._done = False
            self._robot.camera.set_pan_tilt(pan, tilt, wait=wait)
            self._done = True

    @Pyro4.oneway
    def set_tilt(self, tilt, wait=True):
        """Sets the tilt joint angle of robot camera to the specified value.

        :param tilt: value to be set for the tilt joint in radian
        :param wait: wait until the tilt angle is set to
                     the target angle.

        :type tilt: float
        :type wait: bool
        """
        if self._done:
            self._done = False
            self._robot.camera.set_tilt(tilt, wait=wait)
            self._done = True

    # grasping wrapper
    def grasp(self, dims=[(240, 480), (100, 540)]):
        """
        :param dims: List of tuples of min and max indices of the image axis to be considered for grasp search
        :type dims: list
        :return:
        """
        if self._done:
            self._done = False
            # TODO: in reset, pan of camera is set to point to ground, may not need that part
            # success = self._grasper.reset()
            if not success:
                return False
            # grasp_pose = self._grasper.compute_grasp(dims=dims)
            # self._grasper.grasp(grasp_pose)
            self._done = True
            return True

    # slam wrapper
    def explore(self):
        if self._done:
            self._done = False
            if not self._slam.whole_area_explored:
                self._slam.set_goal(
                    (19, 19, 0)
                )  # set  far away goal for exploration, default map size [-20,20]
                self._slam.take_step(self._slam_step_size)
            self._done = True
            return True

    def get_map(self):
        """returns the location of obstacles created by slam only for the obstacles,"""
        # get the index correspnding to obstacles
        indices = np.where(self._slam.map_builder.map[:, :, 1] >= 1.0)
        # convert them into robot frame
        real_world_locations = [
            self._slam.map2real([indice[0], indice[1]]).tolist()
            for indice in zip(indices[0], indices[1])
        ]
        return real_world_locations


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pass in server device IP")
    parser.add_argument(
        "--ip",
        help="Server device (robot) IP. Default is 192.168.0.0",
        type=str,
        default="192.168.0.0",
    )
    parser.add_argument(
        "--backend",
        help="PyRobot backend to use (locobot | habitat). Default is locobot",
        type=str,
        default="locobot",
    )
    parser.add_argument(
        "--backend_config",
        help="Optional config argument to be passed to the backend."
        "Currently mainly used to pass Habitat environment path",
        type=json.loads,
        default='{"scene_path": "/Replica-Dataset/apartment_0/habitat/mesh_semantic.ply", \
            "physics_config": "DEFAULT"}',
    )
    parser.add_argument(
         "--noisy",
        type=bool,
        default=os.getenv("NOISY_HABITAT", "False").lower() in ("true", "True"),
        help="Set to True to load habitat with rgb, depth and movement noise models"
    )

    args = parser.parse_args()

    np.random.seed(123)

    if args.backend == "habitat":
        # GLContexts in general are thread local
        # The PyRobot <-> Habitat integration is not thread-aware / thread-configurable,
        # so our only option is to disable Pyro4's threading, and instead switch to
        # multiplexing (which isn't too bad)
        Pyro4.config.SERVERTYPE = "multiplex"

    with Pyro4.Daemon(args.ip) as daemon:
        robot = RemoteLocobot(
            backend=args.backend, 
            backend_config=args.backend_config,
            noisy=args.noisy,
        )
        robot_uri = daemon.register(robot)
        with Pyro4.locateNS() as ns:
            ns.register("remotelocobot", robot_uri)

        print("Server is started...")
        daemon.requestLoop()


# Below is client code to run in a separate Python shell...
# import Pyro4
# robot = Pyro4.Proxy("PYRONAME:remotelocobot")
# robot.go_home()
