"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import time

from droidlet.parallel import BackgroundTask
from droidlet.perception.robot.handlers import (
    ObjectDetection,
    FaceRecognition,
    HumanPose,
    ObjectTracking,
    DetectLaserPointer,
    ObjectDeduplicator,
)
from droidlet.interpreter.robot.objects import AttributeDict
from droidlet.event import sio
import queue


class Perception:
    """Home for all perceptual modules used by the LocobotAgent.

    It provides a multiprocessing mechanism to run the more compute intensive perceptual
    models (for example our object detector) as a separate process.

    Args:
        model_data_dir (string): path for all perception models (default: ~/locobot/agent/models/perception)
    """

    def __init__(self, model_data_dir):
        self.model_data_dir = model_data_dir

        def slow_perceive_init(weights_dir):
            return AttributeDict(
                {
                    "detector": ObjectDetection(weights_dir),
                    "human_pose": HumanPose(weights_dir),
                    "face_recognizer": FaceRecognition(),
                    "tracker": ObjectTracking(),
                })

        def slow_perceive_run(models, rgb_depth, xyz):
            detections = models.detector(rgb_depth)
            humans = models.human_pose(rgb_depth)
            face_detections = models.face_recognizer(rgb_depth)
            if face_detections:
                detections += face_detections
            return rgb_depth, detections, humans, xyz

        self.vprocess = BackgroundTask(init_fn=slow_perceive_init,
                                   init_args=(model_data_dir,),
                                    process_fn=slow_perceive_run)
        self.vprocess.start()
        self.slow_vision_ready = True

        self.vision = self.setup_vision_handlers()
        self.audio = None
        self.tactile = None

        self.log_settings = {
            "image_resolution": 512,  # pixels
            "image_quality": 10,  # from 10 to 100, 100 being best
        }

        @sio.on("update_image_settings")
        def update_log_settings(sid, new_values):
            self.log_settings["image_resolution"] = new_values["image_resolution"]
            self.log_settings["image_quality"] = new_values["image_quality"]
            sio.emit("image_settings", self.log_settings)

    def setup_vision_handlers(self):
        """Setup all vision handlers, by defining an attribute dict of different perception handlers."""
        handlers = AttributeDict(
            {
                "deduplicate": ObjectDeduplicator(),
            }
        )
        return handlers

    def perceive(self, rgb_depth, xyz, previous_objects, force=False):
        """Called by the core event loop for the agent to run all perceptual
        models and save their state to memory. It fetches the results of
        SlowPerception if they are ready.

        Args:
            force (boolean): set to True to force waiting on the SlowPerception models to finish, and execute
                all perceptual models to execute sequentially (doing that is a good debugging tool)
                (default: False)
        """
        if self.slow_vision_ready:
            self.vprocess.put(rgb_depth, xyz)
            self.slow_vision_ready = False

        try:
            old_image, detections, humans, old_xyz = self.vprocess.get(block=force)
            self.slow_vision_ready = True
        except queue.Empty:
            old_image, detections, humans, old_xyz = None, None, None, None

        self.log(rgb_depth, detections, humans, old_image)
        if detections is not None:
            current_objects = detections + humans
            if previous_objects is not None:
                new_objects, updated_objects = self.vision.deduplicate(
                    current_objects, previous_objects
                )
            return (new_objects, updated_objects)
        return None

    def log(self, rgb_depth, detections, humans, old_rgb_depth):
        """Log all relevant data from the perceptual models for the dashboard.

        All the data here is sent to the dashboard using a socketio emit event. This data
        is then used by the dashboard for different debugging visualizations. Add any data
        that you would want to fetch on the dashboard here.

        Args:
            rgb_depth (RGBDepth): the current RGBDepth frame. This frame might be different from
            old_rgb_depth, which is the RGBDepth frame for which SlowPerception has been run
            detections (list[Detections]): list of all detections
            humans (list[Human]): list of all humans detected
            old_rgb_depth (RGBDepth): RGBDepth frame for which detections and humans are being sent.
            This is the frame for which SlowPerception has been run.

        """
        if hasattr(sio, "mock"):
            return

        sio.emit("image_settings", self.log_settings)
        resolution = self.log_settings["image_resolution"]
        quality = self.log_settings["image_quality"]


        serialized_image = rgb_depth.to_struct(resolution, quality)

        if old_rgb_depth is not None:
            serialized_object_image = old_rgb_depth.to_struct(resolution, quality)
        else:
            serialized_object_image = -1
        serialized_objects = [x.to_struct() for x in detections] if detections is not None else []
        serialized_humans = [x.to_struct() for x in humans] if humans is not None else []

        sio.emit("rgb", serialized_image["rgb"])
        sio.emit("depth", {
            "depthImg": serialized_image["depth_img"],
            "depthMax": serialized_image["depth_max"],
            "depthMin": serialized_image["depth_min"],
        })

        sio.emit("objects", {
            "image": serialized_object_image,
            "objects": serialized_objects,
            })
        sio.emit("humans", {
            "image": serialized_object_image,
            "humans": serialized_humans,
            })
