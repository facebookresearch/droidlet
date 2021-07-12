"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import unittest
import numpy as np
from numpy.testing import assert_allclose
from droidlet.lowlevel.robot_mover_utils import xyz_canonical_coords_to_pyrobot_coords
from droidlet.perception.robot import Detection
from droidlet.shared_data_structs import RGBDepth
from droidlet.memory.robot.loco_memory import LocoAgentMemory
from droidlet.memory.robot.loco_memory_nodes import DetectedObjectNode, HumanPoseNode
from droidlet.perception.robot.tests.utils import get_fake_detection, get_fake_humanpose, get_fake_bbox
from droidlet.interpreter.robot import dance


class MemoryTests(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(MemoryTests, self).__init__(*args, **kwargs)
        self.memory = LocoAgentMemory()
        dance.add_default_dances(self.memory)

    def test_detected_object_node_creation(self):
        d = get_fake_detection(
            "smaug", ["red_golden", "dragon", "lonely_mountain"], [-0.4, -0.08, 0.0]
        )
        DetectedObjectNode.create(self.memory, d)

        # Check that class_label, properties are saved as tags
        tags_to_check = ["red_golden", "dragon", "lonely_mountain", "smaug"]
        for x in tags_to_check:
            t = self.memory.get_detected_objects_tagged(x)
            self.assertEqual(len(t), 1)
    
    def test_detected_object_3dbbox(self):
        # Artificially create a mask of the first 10*10 pixels in a fixed size image
        # x increases horizontally, y increases vertically, z is constant.
        # Check that the returned axis aligned bbox alignes with the values in this 10*10 patch.

        p = 100
        xs = np.sort(np.random.uniform(0, 10, p))
        xs = np.tile(xs, (p, 1))

        ys = np.sort(np.random.uniform(0, 10, p))
        ys[::-1].sort()
        ys = np.transpose(np.tile(ys, (p,1)))

        # (x,y,z=1) in row-major form, in locobot coords
        pts = np.asarray([xyz_canonical_coords_to_pyrobot_coords((x,y,1))
            for x,y in zip(xs.ravel(), ys.ravel())])
        
        depth = np.ones((p, p))
        rgb = np.float32(np.random.rand(p, p, 3) * 255)

        rgb_d = RGBDepth(rgb, depth, pts)
        
        mask = np.zeros((p,p), dtype=bool)
        for x in np.arange(10):
            for y in np.arange(10):
                mask[x][y] = 1

        # expected bounds of the detection minx, miny, minz, maxx, maxy, maxz
        exp_bounds = (xs[0][0], ys[9][0], 1.0, xs[0][9], ys[0][0], 1.0)

        d = Detection(
            rgb_d,
            class_label="3dbbox_test",
            properties="properties",
            mask=mask,
            bbox=get_fake_bbox(),
            center=(5,5)
        )
        b = d.get_bounds()

        DetectedObjectNode.create(self.memory, d)
        o = DetectedObjectNode.get_all(self.memory)
        self.assertEqual(len(o), 1) # assert only one detection retrieved
        assert_allclose(b, o[0]['bounds']) # assert created bounds are same as retreieved.
        assert_allclose(o[0]['bounds'], exp_bounds) # assert bounds retrieved are same as expected.


    def test_humanpose_node_creation(self):
        h = get_fake_humanpose()
        HumanPoseNode.create(self.memory, h)

        # Check that _human_pose is a tag as per implementation
        tags_to_check = ["_human_pose"]
        for x in tags_to_check:
            t = self.memory.get_detected_objects_tagged(x)
            self.assertEqual(len(t), 1)


if __name__ == "__main__":
    unittest.main()
