# need to convert it to api
from pyrobot import Robot

import os
import numpy as np
import sys
import matplotlib.pyplot as plt
from pyrobot.utils.util import try_cv2_import
import argparse
from scipy import ndimage
from copy import deepcopy as copy
import time
from math import ceil, floor
import sys
import json
from pyrobot.locobot.base_control_utils import LocalActionStatus

cv2 = try_cv2_import()

# for slam modules
sys.path.append(os.path.join(os.path.dirname(__file__), "../"))
from skimage.morphology import disk, binary_dilation
from slam_pkg.utils.map_builder import MapBuilder as mb
from slam_pkg.utils.fmm_planner import FMMPlanner
from slam_pkg.utils import depth_util as du


class Slam(object):
    def __init__(
        self,
        robot,
        robot_name,
        map_size=4000,
        resolution=5,
        robot_rad=25,
        agent_min_z=5,
        agent_max_z=70,
        vis=False,
        save_vis=os.getenv("SAVE_VIS", 'False').lower() in ('true', 'True'),
        save_folder=os.getenv("SLAM_SAVE_FOLDER", '../slam_logs'),
    ):
        """

        :param robot: pyrobot robot object, only supports [habitat, locobot]
        :param robot_name: name of the robot [habitat, locobot] 
        :param map_size: size of map to be build in cm, assumes square map
        :param resolution: resolution of map, 1 pix = resolution distance(in cm) in real world
        :param robot_rad: radius of the agent, used to explode the map
        :param agent_min_z: robot min z (in cm), depth points below this will be considered as free space
        :param agent_max_z: robot max z (in cm), depth points above this will be considered as free space
        :param vis: whether to show visualization
        :param save_vis: whether to save visualization
        :param save_folder: path to save visualization

        :type robot: pytobot.Robot
        :type robot_name: str
        :type map_size: int
        :type resolution: int
        :type robot_rad: int
        :type agent_min_z: int
        :type agent_max_z: int
        :type vis: bool
        :type save_vis: bool
        :type save_folder: str
        """
        self.robot = robot
        self.robot_name = robot_name
        self.robot_rad = robot_rad
        self.map_builder = mb(
            map_size_cm=map_size,
            resolution=resolution,
            agent_min_z=agent_min_z,
            agent_max_z=agent_max_z,
        )

        # initialize variable
        robot.camera.reset()
        time.sleep(2)

        self.init_state = self.get_robot_global_state()
        self.prev_bot_state = (0, 0, 0)
        self.col_map = np.zeros((self.map_builder.map.shape[0], self.map_builder.map.shape[1]))
        self.robot_loc_list_map = np.array(
            [
                self.real2map(
                    self.get_rel_state(self.get_robot_global_state(), self.init_state)[:2]
                )
            ]
        )
        self.map_builder.update_map(
            self.robot.camera.get_current_pcd(in_cam=False)[0],
            self.get_rel_state(self.get_robot_global_state(), self.init_state),
        )

        # for visualization purpose #
        self.vis = vis
        self.save_vis = save_vis
        self.save_folder = save_folder
        print(f"save_vis {save_vis}, save_folder {save_folder}")
        # to visualize robot heading
        triangle_scale = 0.5
        self.triangle_vertex = np.array([[0.0, 0.0], [-2.0, 1.0], [-2.0, -1.0]])
        self.triangle_vertex *= triangle_scale
        if self.save_vis:
            self.save_folder = save_folder
            self.img_folder = os.path.join(self.save_folder, "rgb")
            self.depth_folder = os.path.join(self.save_folder, "depth")
            self.seg_folder = os.path.join(self.save_folder, "seg")
            if not os.path.isdir(self.save_folder):
                os.makedirs(self.save_folder)

            if not os.path.isdir(self.img_folder):
                os.makedirs(self.img_folder)

            if not os.path.isdir(self.depth_folder):
                os.makedirs(self.depth_folder)

            if not os.path.isdir(self.seg_folder):
                os.makedirs(self.seg_folder)
        
        self.last_pos = self.robot.base.get_state()

        self.start_vis = False
        self.vis_count = 0
        self.skp =0

        # for bumper check of locobot
        if self.robot_name == "locobot":
            from slam_pkg.utils.locobot_bumper_checker import BumperCallbacks

            self.bumper_state = BumperCallbacks()
            # for mapping refer to http://docs.ros.org/groovy/api/kobuki_msgs/html/msg/BumperEvent.html
            self.bumper_num2ang = {0: np.deg2rad(30), 1: 0, 2: np.deg2rad(-30)}

        self.whole_area_explored = False

        # for storing data
        self.img_count = 0
        self.pos_dic = {}
        self.exec_wait = not (self.save_vis)

    def set_goal(self, goal):
        """
        goal is 3 len tuple with position in real world in robot start frame
        :param goal: goal to be reached in metric unit

        :type goal: tuple

        :return:
        """
        self.goal_loc = goal
        self.goal_loc_map = self.real2map(self.goal_loc[:2])

    def set_relative_goal_in_robot_frame(self, goal):
        """
        goal is 3 len tuple with position in real world in robot current frmae
        :param goal: goal to be reached in metric unit

        :type goal: tuple

        :return:
        """
        robot_pr_pose = self.get_robot_global_state()
        # check this part
        abs_pr_goal = list(self.get_rel_state(goal, (0.0, 0.0, -robot_pr_pose[2])))
        abs_pr_goal[0] += robot_pr_pose[0]
        abs_pr_goal[1] += robot_pr_pose[1]
        abs_pr_goal[2] = goal[2] + robot_pr_pose[2]

        # convert the goal in init frame
        self.goal_loc = self.get_rel_state(abs_pr_goal, self.init_state)
        self.goal_loc_map = self.real2map(self.goal_loc[:2])

        # TODO: make it non blocking
        while self.take_step(25) is None:
            continue

    def set_absolute_goal_in_robot_frame(self, goal):
        """
        goal is 3 len tuple with position in real world in robot start frmae
        :param goal: goal to be reached in metric unit

        :type goal: tuple

        :return:
        """
        # convert the relative goal to abs goal
        self.goal_loc = self.get_rel_state(goal, self.init_state)
        # convert the goal in inti frame
        self.goal_loc_map = self.real2map(self.goal_loc[:2])

        # TODO make it non blocking
        while self.take_step(25) is None:
            continue

    def update_map(self):
        """Updtes map , explode it by the radius of robot, add collison map to it and return the traversible area

        Returns:
            [np.ndarray]: [traversible space]
        """
        robot_state = self.get_rel_state(self.get_robot_global_state(), self.init_state)
        self.map_builder.update_map(
            self.robot.camera.get_current_pcd(in_cam=False)[0], robot_state
        )

        # explode the map by robot shape
        obstacle = self.map_builder.map[:, :, 1] >= 1.0
        selem = disk(self.robot_rad / self.map_builder.resolution)
        traversable = binary_dilation(obstacle, selem) != True

        # add robot collision map to traversable area
        unknown_region = self.map_builder.map.sum(axis=-1) < 1
        col_map_unknown = np.logical_and(self.col_map > 0.1, unknown_region)
        traversable = np.logical_and(traversable, np.logical_not(col_map_unknown))
        return traversable

    def take_step(self, step_size):
        """
        step size in meter
        :param step_size:
        :return:
        """
        # update map
        traversable = self.update_map()

        # call the planner
        self.planner = FMMPlanner(
            traversable, step_size=int(step_size / self.map_builder.resolution)
        )

        # set the goal
        self.planner.set_goal(self.goal_loc_map)

        # get the short term goal
        robot_map_loc = self.real2map(
            self.get_rel_state(self.get_robot_global_state(), self.init_state)
        )
        self.stg = self.planner.get_short_term_goal((robot_map_loc[1], robot_map_loc[0]))

        # convert goal from map space to robot space
        stg_real = self.map2real([self.stg[1], self.stg[0]])
        print("stg = {}".format(self.stg))
        print("stg real = {}".format(stg_real))

        # convert stg real from init frame to global frame of pyrobot
        stg_real_g = self.get_absolute_goal((stg_real[0], stg_real[1], 0))
        robot_state = self.get_rel_state(self.get_robot_global_state(), self.init_state)
        print("bot_state before executing action = {}".format(robot_state))

        # orient the robot
        exec = self.robot.base.go_to_relative(
            (
                0,
                0,
                np.arctan2(
                    stg_real[1] - self.prev_bot_state[1], stg_real[0] - self.prev_bot_state[0]
                )
                - robot_state[2],
            ),
            wait=self.exec_wait,
        )
        while self.robot.base._as.get_state() == LocalActionStatus.ACTIVE:
            if self.save_vis:
                self.save_rgb_depth_seg()
            else:
                pass

        # update map
        traversable = self.update_map()

        """
        # add robot collision map to traversable area
        # commented it as on real robot this gives issue sometime
        unknown_region = self.map_builder.map.sum(axis=-1) < 1
        col_map_unknown = np.logical_and(self.col_map > 0.1, unknown_region)
        traversable = np.logical_and(traversable, np.logical_not(col_map_unknown))
        """

        # check whether goal is on collision
        if not np.logical_or.reduce(
            traversable[
                floor(self.stg[0]) : ceil(self.stg[0]), floor(self.stg[1]) : ceil(self.stg[1])
            ],
            axis=(0, 1),
        ):
            print("Obstacle in path")
        else:
            # go to the location the robot
            exec = self.robot.base.go_to_absolute(
                (
                    stg_real_g[0],
                    stg_real_g[1],
                    np.arctan2(
                        stg_real[1] - self.prev_bot_state[1], stg_real[0] - self.prev_bot_state[0]
                    )
                    + self.init_state[2],
                ),
                wait=self.exec_wait,
            )
            while self.robot.base._as.get_state() == LocalActionStatus.ACTIVE:
                if self.save_vis:
                    self.save_rgb_depth_seg()
                else:
                    pass

        robot_state = self.get_rel_state(self.get_robot_global_state(), self.init_state)
        print("bot_state after executing action = {}".format(robot_state))

        # update robot location list
        robot_state_map = self.real2map(robot_state[:2])
        self.robot_loc_list_map = np.concatenate(
            (self.robot_loc_list_map, np.array([robot_state_map]))
        )
        self.prev_bot_state = robot_state

        # if robot collides
        if not exec:
            # add obstacle in front of  cur location
            self.col_map += self.get_collision_map(robot_state)
        # in case of locobot we need to check bumper state
        if self.robot_name == "locobot":
            if len(self.bumper_state.bumper_state) > 0:
                for bumper_num in self.bumper_state.bumper_state:
                    self.col_map += self.get_collision_map(
                        (
                            robot_state[0],
                            robot_state[1],
                            robot_state[2] + self.bumper_num2ang[bumper_num],
                        )
                    )

        # return True if robot reaches within threshold
        if (
            np.linalg.norm(np.array(robot_state[:2]) - np.array(self.goal_loc[:2])) * 100.0
            < np.sqrt(2) * self.map_builder.resolution
        ):
            self.robot.base.go_to_absolute(
                self.get_absolute_goal(self.goal_loc), wait=self.exec_wait
            )
            print("robot has reached goal")
            while self.robot.base._as.get_state() == LocalActionStatus.ACTIVE:
                if self.save_vis:
                    self.save_rgb_depth_seg()
                else:
                    pass
            return True

        # return False if goal is not reachable
        if not traversable[int(self.goal_loc_map[1]), int(self.goal_loc_map[0])]:
            print("Goal Not reachable")
            return False
        if (
            self.planner.fmm_dist[int(robot_state_map[1]), int(robot_state_map[0])]
            >= self.planner.fmm_dist.max()
        ):
            print("whole area is explored")
            self.whole_area_explored = True
            return False
        return None

    def save_rgb_depth_seg(self):
        rgb, depth, seg = self.robot.camera.get_rgb_depth_segm()
        pos = self.robot.base.get_state()
        self.skp += 1
        if pos != self.last_pos and self.skp % 10 == 0:
            self.last_pos = pos
            # store the images and depth
            cv2.imwrite(
                self.img_folder + "/{:05d}.jpg".format(self.img_count),
                cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB),
            )

            # store depth in mm
            depth *= 1e3
            depth[depth > np.power(2, 16) - 1] = np.power(2, 16) - 1
            depth = depth.astype(np.uint16)
            np.save(self.depth_folder + "/{:05d}.npy".format(self.img_count), depth)

            # store seg
            np.save(self.seg_folder + "/{:05d}.npy".format(self.img_count), seg)

            # store pos
            self.pos_dic[self.img_count] = copy(pos)
            self.img_count += 1
            print(f"img_count {self.img_count}, skp {self.skp}, base_pos {pos}")
            with open(os.path.join(self.save_folder, "data.json"), "w") as fp:
                json.dump(self.pos_dic, fp)

    def get_absolute_goal(self, loc):
        """
        Transfer loc in init robot frame to global frame
        :param loc: location in init frame in metric unit

        :type loc: tuple

        :return: location in global frame in metric unit
        :rtype: list
        """
        # 1) orient goal to global frame
        loc = self.get_rel_state(loc, (0.0, 0.0, -self.init_state[2]))

        # 2) add the offset
        loc = list(loc)
        loc[0] += self.init_state[0]
        loc[1] += self.init_state[1]
        return tuple(loc)

    def real2map(self, loc):
        """
        convert real world location to map location
        :param loc: real world location in metric unit

        :type loc: tuple

        :return: location in map space
        :rtype: tuple [x_map_pix, y_map_pix]
        """
        # converts real location to map location
        loc = np.array([loc[0], loc[1], 0])
        loc *= 100  # convert location to cm
        map_loc = du.transform_pose(
            loc,
            (self.map_builder.map_size_cm / 2.0, self.map_builder.map_size_cm / 2.0, np.pi / 2.0),
        )
        map_loc /= self.map_builder.resolution
        map_loc = map_loc.reshape(3)
        return tuple(map_loc[:2])

    def map2real(self, loc):
        """
        convert map location to real world location
        :param loc: map location [x_pixel_location, y_pixel_location]

        :type loc: list

        :return: corresponding map location in real world in metric unit
        :rtype: list [x_real_world, y_real_world]
        """
        # converts map location to real location
        loc = np.array([loc[0], loc[1], 0])
        real_loc = du.transform_pose(
            loc,
            (
                -self.map_builder.map.shape[0] / 2.0,
                self.map_builder.map.shape[1] / 2.0,
                -np.pi / 2.0,
            ),
        )
        real_loc *= self.map_builder.resolution  # to take into account map resolution
        real_loc /= 100  # to convert from cm to meter
        real_loc = real_loc.reshape(3)
        return real_loc[:2]

    def get_collision_map(self, state, obstacle_size=(10, 10)):
        """
        Helpful for creating collision map based on the bumper sensor reading.
        Creates collision map based on robot current location (in real world frame) and obstacle size
        :param state: robot state in metric unit
        :param obstacle_size: size of obstacle in map space

        :type state: tuple
        :type obstacle_size: tuple

        :return: collision map
        :rtype: np.ndarray
        """
        # get the collision map for robot collision based on sensor reading
        col_map = np.zeros((self.map_builder.map.shape[0], self.map_builder.map.shape[1]))
        map_state = self.real2map((state[0], state[1]))
        map_state = [int(x) for x in map_state]
        center_map_state = self.real2map((0, 0))
        center_map_state = [int(x) for x in center_map_state]
        col_map[
            center_map_state[1] + 2 : center_map_state[1] + 2 + obstacle_size[1],
            center_map_state[0]
            - int(obstacle_size[0] / 2) : center_map_state[0]
            + int(obstacle_size[0] / 2),
        ] = True

        # rotate col_map based on the state
        col_map = ndimage.rotate(col_map, -np.rad2deg(state[2]), reshape=False)

        # take crop around the center
        pad_len = 2 * max(obstacle_size)
        cropped_map = copy(
            col_map[
                center_map_state[1] - pad_len : center_map_state[1] + pad_len,
                center_map_state[0] - pad_len : center_map_state[0] + pad_len,
            ]
        )

        # make the crop value zero
        col_map = np.zeros((self.map_builder.map.shape[0], self.map_builder.map.shape[1]))

        # pad the col_map
        col_map = np.pad(col_map, pad_len)

        # paste the crop robot location shifted by pad len
        col_map[
            map_state[1] - pad_len + pad_len : map_state[1] + pad_len + pad_len,
            map_state[0] - pad_len + pad_len : map_state[0] + pad_len + pad_len,
        ] = cropped_map
        return col_map[pad_len:-pad_len, pad_len:-pad_len]

    def get_rel_state(self, cur_state, init_state):
        """
        helpful for calculating the relative state of cur_state wrt to init_state [both states are wrt same frame]
        :param cur_state: frame for which position to be calculated
        :param init_state: frame in which position to be calculated

        :type cur_state: tuple [x_robot, y_robot, yaw_robot]
        :type init_state: tuple [x_robot, y_robot, yaw_robot]

        :return: relative state of cur_state wrt to init_state
        :rtype list [x_robot_rel, y_robot_rel, yaw_robot_rel]
        """
        # get relative in global frame
        rel_X = cur_state[0] - init_state[0]
        rel_Y = cur_state[1] - init_state[1]
        # transfer from global frame to init frame
        R = np.array(
            [
                [np.cos(init_state[2]), np.sin(init_state[2])],
                [-np.sin(init_state[2]), np.cos(init_state[2])],
            ]
        )
        rel_x, rel_y = np.matmul(R, np.array([rel_X, rel_Y]).reshape(-1, 1))
        return rel_x[0], rel_y[0], cur_state[2] - init_state[2]

    def get_robot_global_state(self):
        """
        :return: return the global state of the robot [x_robot_loc, y_robot_loc, yaw_robot]
        :rtype: tuple
        """
        return self.robot.base.get_state("odom")

    def visualize(self):
        """

        :return:
        """

        def vis_env_agent_state():
            # goal
            plt.plot(self.goal_loc_map[0], self.goal_loc_map[1], "y*")
            # short term goal
            plt.plot(self.stg[1], self.stg[0], "b*")
            plt.plot(self.robot_loc_list_map[:, 0], self.robot_loc_list_map[:, 1], "r--")

            # draw heading of robot
            robot_state = self.get_rel_state(self.get_robot_global_state(), self.init_state)
            R = np.array(
                [
                    [np.cos(robot_state[2]), np.sin(robot_state[2])],
                    [-np.sin(robot_state[2]), np.cos(robot_state[2])],
                ]
            )
            global_tri_vertex = np.matmul(R.T, self.triangle_vertex.T).T
            map_global_tra_vertex = np.array(
                [
                    self.real2map((x[0] + robot_state[0], x[1] + robot_state[1]))
                    for x in global_tri_vertex
                ]
            )
            t1 = plt.Polygon(map_global_tra_vertex, color="red")
            plt.gca().add_patch(t1)

        if not self.start_vis:
            plt.figure(figsize=(40, 8))
            self.start_vis = True
        plt.clf()
        num_plots = 4

        # visualize RGB image
        plt.subplot(1, num_plots, 1)
        plt.title("RGB")
        plt.imshow(self.robot.camera.get_rgb())

        # visualize Depth image
        plt.xticks([])
        plt.yticks([])
        plt.subplot(1, num_plots, 2)
        plt.title("Depth")
        plt.imshow(self.robot.camera.get_depth())

        # visualize distance to goal & map, robot current location, goal, short term goal, robot path #
        plt.xticks([])
        plt.yticks([])
        plt.subplot(1, num_plots, 3)
        plt.title("Dist to Goal")
        plt.imshow(self.planner.fmm_dist, origin="lower")
        vis_env_agent_state()

        plt.subplot(1, num_plots, 4)
        plt.title("Map")
        plt.imshow(self.map_builder.map[:, :, 1] >= 1.0, origin="lower")
        vis_env_agent_state()

        plt.gca().set_aspect("equal", adjustable="box")
        if self.save_vis:
            plt.savefig(os.path.join(self.save_folder, "{:04d}.jpg".format(self.vis_count)))
        if self.vis:
            plt.pause(0.1)
        self.vis_count += 1


def main(args):
    if args.robot == "habitat":
        assets_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../test/test_assets")
        )
        scene = args.scene
        time.sleep(10.0)
        try:
            config = {
                "physics_config": os.path.join(assets_path, "default.phys_scene_config.json"),
                "scene_path": "{}/{}/habitat/mesh_semantic.ply".format(args.dataset_path, scene),
            }
            args.store_path = "./tmp/{}".format(scene)
            robot = Robot("habitat", common_config=config)
            agent_state = robot.base.agent.get_state()
            # place the robot at place where it can move
            p = robot.base.sim.pathfinder.get_random_navigable_point()

            agent_state.position = copy(p)
            agent_state.sensor_states["rgb"].position = copy(p + np.array([0.0, 0.6, 0.0]))
            agent_state.sensor_states["depth"].position = copy(p + np.array([0.0, 0.6, 0.0]))
            agent_state.sensor_states["semantic"].position = copy(p + np.array([0.0, 0.6, 0.0]))
            robot.base.agent.set_state(agent_state)
            print("trying scene = {}".format(scene))

            slam = Slam(
                robot,
                args.robot,
                args.map_size,
                args.resolution,
                args.robot_rad,
                args.agent_min_z,
                args.agent_max_z,
                args.vis,
                args.save_vis,
                args.store_path,
            )
            slam.set_goal(tuple(args.goal))
            while slam.take_step(step_size=args.step_size) is None:
                slam.visualize()

            # save pos dic
            with open(os.path.join(slam.save_folder, "data.json"), "w") as fp:
                json.dump(slam.pos_dic, fp)
            slam.visualize()

            """
            # helpful visualizing the exploration
            #TODO: to make it work need to install ffmpeg to cker image
            # generate gif out of plt images
            os.system(
                "ffmpeg -framerate 6 -f image2 -i {}/%04d.jpg {}/exploration.gif".format(
                    slam.save_folder, slam.save_folder
                )
            )

            # rm plt images
            os.system("rm {}/*.jpg".format(slam.save_folder))
            """
        except:
            print("not able to open the scene = {}".format(scene))

    elif args.robot == "locobot":
        robot = Robot("locobot")
        slam = Slam(
            robot,
            args.robot,
            args.map_size,
            args.resolution,
            args.robot_rad,
            args.agent_min_z,
            args.agent_max_z,
            args.vis,
            args.save_vis,
            args.store_path,
        )
        slam.set_goal(tuple(args.goal))
        while slam.take_step(step_size=args.step_size) is None:
            slam.visualize()

        # save pos dic
        with open(os.path.join(slam.save_folder, "data.json"), "w") as fp:
            json.dump(slam.pos_dic, fp)
        slam.visualize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Args for testing simple SLAM algorithm")
    parser.add_argument(
        "--robot", help="Name of the robot [locobot, habitat]", type=str, default="habitat"
    )
    parser.add_argument(
        "--goal", help="goal the robot should reach in metric unit", nargs="+", type=float
    )
    parser.add_argument("--map_size", help="lenght and with of map in cm", type=int, default=4000)
    parser.add_argument(
        "--resolution", help="per pixel resolution of map in cm", type=int, default=5
    )
    parser.add_argument("--step_size", help="step size in cm", type=int, default=25)
    parser.add_argument("--robot_rad", help="robot radius in cm", type=int, default=25)
    parser.add_argument("--agent_min_z", help="agent min height in cm", type=int, default=5)
    parser.add_argument("--agent_max_z", help="robot max height in cm", type=int, default=70)
    parser.add_argument("--vis", help="whether to show visualization", action="store_true")
    parser.add_argument("--save_vis", help="whether to store visualization", action="store_true")
    parser.add_argument(
        "--store_path", help="path to store visualization", type=str, default="./tmp"
    )
    parser.add_argument(
        "--dataset_path",
        help="path where Replica dataset is stored",
        type=str,
        default="/Replica-Dataset",
    )
    parser.add_argument(
        "--scene", help="scence name for data collection", type=str, default="apartment_0"
    )
    args = parser.parse_args()
    main(args)
