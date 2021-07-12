"""
Copyright (c) Facebook, Inc. and its affiliates.
"""

import logging
import sys
import os
import open3d as o3d
from abc import abstractmethod
import numpy as np
from PIL import Image

if "/opt/ros/kinetic/lib/python2.7/dist-packages" in sys.path:
    sys.path.remove("/opt/ros/kinetic/lib/python2.7/dist-packages")
import cv2

from droidlet.perception.robot.perception_helpers import get_color_tag
from droidlet.lowlevel.robot_mover_utils import xyz_pyrobot_to_canonical_coords

class AbstractHandler:
    """Interface for implementing perception handlers.

    Each handler must implement the handle and an optional _debug_draw method.
    """

    @abstractmethod
    def __call__(self, *input):
        """Implement this method to hold the core execution logic."""
        pass

    def _debug_draw(self, *input):
        """Implement this method to hold visualization details useful in
        debugging."""
        raise NotImplementedError


class WorldObject:
    def __init__(self, label, center, rgb_depth, mask=None, xyz=None):
        self.label = label
        self.center = center
        self.rgb_depth = rgb_depth
        self.mask = mask
        self.xyz = xyz if xyz else rgb_depth.get_coords_for_point(self.center)
        self.eid = None
        self.feature_repr = None
        self.bounds = rgb_depth.get_bounds_for_mask(self.mask) 

    def get_xyz(self):
        """returns xyz in canonical world coordinates."""
        return {"x": self.xyz[0], "y": self.xyz[1], "z": self.xyz[2]}
    
    def get_bounds(self):
        """returns bounding box as dict."""
        return (self.bounds[0], self.bounds[1], self.bounds[2],
            self.bounds[3], self.bounds[4], self.bounds[5])

    def get_masked_img(self):
        raise NotImplementedError

    def save_to_memory(self):
        raise NotImplementedError

    def to_struct(self):
        raise NotImplementedError


