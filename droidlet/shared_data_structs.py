import numpy as np
import time
from droidlet.lowlevel.locobot.locobot_mover_utils import xyz_pyrobot_to_canonical_coords
from droidlet.base_util import TICKS_PER_SEC


class Time:
    def __init__(self):
        self.init_time_raw = time.time()

    # converts from seconds to internal tick
    def round_time(self, t):
        return int(TICKS_PER_SEC * t)

    def get_time(self):
        return self.round_time(time.time() - self.init_time_raw)

    def get_world_hour(self):
        # returns a fraction of a day.  0 is sunrise, .5 is sunset, 1.0 is next day
        return (time.localtime()[3] - 8 + time.localtime()[4] / 60) / 24

    def add_tick(self, ticks=1):
        time.sleep(ticks / TICKS_PER_SEC)


class ErrorWithResponse(Exception):
    def __init__(self, chat):
        self.chat = chat


class NextDialogueStep(Exception):
    pass


class RGBDepth:
    """Class for the current RGB, depth and point cloud fetched from the robot.

    Args:
        rgb (np.array): RGB image fetched from the robot
        depth (np.array): depth map fetched from the robot
        pts (np.array [(x,y,z)]): array of x,y,z coordinates of the pointcloud corresponding
        to the rgb and depth maps.
    """

    rgb: np.array
    depth: np.array
    ptcloud: np.array

    def __init__(self, rgb, depth, pts):
        self.rgb = rgb
        self.depth = depth
        self.ptcloud = pts.reshape(rgb.shape)

    def get_pillow_image(self):
        from PIL import Image
        return Image.fromarray(self.rgb, "RGB")

    def get_bounds_for_mask(self, mask):
        import open3d as o3d
        """for all points in the mask, returns the bounds as an axis-aligned bounding box.
        """
        if mask is None:
            return None
        points = self.ptcloud[np.where(mask == True)]
        points = xyz_pyrobot_to_canonical_coords(points)
        points = o3d.utility.Vector3dVector(points)
        obb = o3d.geometry.AxisAlignedBoundingBox.create_from_points(points)
        return np.concatenate([obb.get_min_bound(), obb.get_max_bound()])

    def get_coords_for_point(self, point):
        """fetches xyz from the point cloud in pyrobot coordinates and converts it to
        canonical world coordinates.
        """
        if point is None:
            return None
        xyz_p = self.ptcloud[point[1], point[0]]
        return xyz_pyrobot_to_canonical_coords(xyz_p)

    def to_struct(self, size=None, quality=10):
        import cv2
        import base64

        rgb = self.rgb
        depth = self.depth

        if size is not None:
            rgb = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_LINEAR)
            depth = cv2.resize(depth, (size, size), interpolation=cv2.INTER_LINEAR)

        depth_img = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX)
        depth_img = 255 - depth_img

        # webp seems to be better than png and jpg as a codec, in both compression and quality
        encode_param = [int(cv2.IMWRITE_WEBP_QUALITY), quality]
        fmt = ".webp"

        _, rgb_data = cv2.imencode(fmt, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), encode_param)
        _, depth_img_data = cv2.imencode(fmt, depth_img, encode_param)
        return {
            "rgb": base64.b64encode(rgb_data).decode("utf-8"),
            "depth_img": base64.b64encode(depth_img_data).decode("utf-8"),
            "depth_max": str(np.max(depth)),
            "depth_min": str(np.min(depth)),
        }


class MockOpt:
    def __init__(self):
        self.no_default_behavior = False
        self.nsp_models_dir = ""
        self.nsp_data_dir = ""
        self.ground_truth_data_dir = ""
        self.semseg_model_path = ""
        self.no_ground_truth = True
        # test does not instantiate cpp client
        self.port = -1
        self.no_default_behavior = False
        self.log_timeline = False
        self.enable_timeline = False
