"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from .core import AbstractHandler
import os
import logging
import numpy as np
import cv2
import torch
import face_recognition as fr
from facenet_pytorch import MTCNN
from .detector import Detection


class FaceRecognition(AbstractHandler):
    """Class for Face Recognition models.

    We use a keypoint estimator.

    Args:
        face_ids_dir (string): path to faces used to seed the face recognizer with
        silent (boolean): boolean to suppress all self.draw() calls
    """

    def __init__(self, face_ids_dir=None):
        if face_ids_dir is None:
            face_ids_dir = os.path.join(os.path.dirname(__file__), "../", "offline_files/faces")

        self.faces_path = face_ids_dir
        self.encoded_faces = self.get_encoded_faces()
        self.face_names = []
        self.face_locations = []

    def get_encoded_faces(self):
        """looks through the faces folder and encodes all the faces.

        :return: dict of (name, image encoded)
        """
        encoded = {}
        for dirpath, dnames, fnames in os.walk(self.faces_path):
            for f in fnames:
                if f.endswith(".jpg") or f.endswith(".png"):
                    face = fr.load_image_file(os.path.join(self.faces_path, f))
                    encoding = fr.face_encodings(face)[0]
                    encoded[f.split(".")[0]] = encoding
        return encoded

    @staticmethod
    def overlap(box1, box2):
        """Check if two bounding boxes overlap or not each box's coordinates
        is: (y1, x2, y2, x1)"""

        # If one rectangle is on left side of other
        if box1[3] >= box2[1] or box2[3] >= box1[1]:
            return False

        # If one rectangle is above other
        if box1[0] >= box2[2] or box2[0] >= box1[2]:
            return False
        return True

    @staticmethod
    def get_facenet_boxes(img):
        """get the face locations from facenet module."""

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        mtcnn = MTCNN(
            image_size=160,
            margin=0,
            min_face_size=20,
            thresholds=[0.6, 0.7, 0.7],
            factor=0.709,
            post_process=True,
            device=device,
        )
        face_locations_float, prob, points = mtcnn.detect(img, landmarks=True)
        face_locations = []
        if face_locations_float is not None:
            # convert the location boxes to integer
            for i in face_locations_float:
                face_locations.append([int(j) for j in i])
            # flip the (x1, y1, x2, y2) from facenet to (y1, x2, y2, x1) of face_recognition
            for loc in face_locations:
                y1, x2, y2, x1 = loc[1], loc[2], loc[3], loc[0]
                loc[0], loc[1], loc[2], loc[3] = y1, x2, y2, x1
        return face_locations

    def get_union(self, locations1, locations2):
        """Get the union of two sets of bounding boxes."""
        non_overlap = []
        for i, box1 in enumerate(locations1):
            for j, box2 in enumerate(locations2):
                # check if it intersects with another in the larger set
                if self.overlap(box1, box2):
                    break
                if j == len(locations2) - 1:
                    non_overlap.append(box1)

        return locations2 + non_overlap

    def detect_faces(self, rgb_depth):
        """will find all of the faces in a given image and label them if it
        knows what they are then save them in the object.

        :param rgb_depth: the captured picture by Locobot camera
        """
        faces = self.encoded_faces
        faces_encoded = list(faces.values())
        known_face_names = list(faces.keys())

        img = rgb_depth.rgb
        print(f'rgb type {type(img)}')
        # get the bounding boxes from the face_recognition module
        face_rec_locations = fr.face_locations(img)
        # get the bounding boxes from facenet module
        facenet_locations = self.get_facenet_boxes(img)

        if facenet_locations and face_rec_locations:
            self.face_locations = self.get_union(face_rec_locations, facenet_locations)
        elif facenet_locations:
            self.face_locations = facenet_locations
        elif face_rec_locations:
            self.face_locations = face_rec_locations

        unknown_face_encodings = fr.face_encodings(img, self.face_locations)

        logging.debug(f"Detected {len(self.face_locations)} face(s)")

        for face_encoding in unknown_face_encodings:
            name = "Unknown"

            if len(faces_encoded) > 0:
                # See if the face is a match for the known face(s)
                matches = fr.compare_faces(faces_encoded, face_encoding, tolerance=0.55)

                # use the known face with the smallest distance to the new face
                face_distances = fr.face_distance(faces_encoded, face_encoding)
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = known_face_names[best_match_index]

            self.face_names.append(name)

    def __call__(self, rgb_depth):
        self.detect_faces(rgb_depth)
        logging.info("In FaceDetectionHandler ... ")
        detections = []
        for i, face in enumerate(zip(self.face_names, self.face_locations)):
            name, loc = face
            top, right, bottom, left = loc
            center_point = (int((right - left) / 2 + left), int((bottom - top) / 2 + top))

            # define a mask on the detected face
            mask = np.array(rgb_depth.get_pillow_image())
            h, w = abs(right - left), abs(bottom - top)
            detected_face = mask[top : top + h, left : left + w, :]
            mask[top : top + h, left : left + w] = np.zeros(detected_face.shape, np.uint8)
            bbox = [left, top, right, bottom]

            detections.append(
                Detection(
                    rgb_depth,
                    class_label="person",
                    properties={},
                    mask=mask[:, :, 0],
                    bbox=bbox,
                    face_tag=(name, loc),
                    center=center_point,
                )
            )
        if os.getenv("DEBUG_DRAW") == "True":
            self._debug_draw(rgb_depth, detections)
        return detections

    def _debug_draw(self, rgb_depth, detections):
        img = np.array(rgb_depth.get_pillow_image())
        for d in detections:
            # draw a rectangle on each face
            top, right, bottom, left = d.facial_rec_tag[1]
            name = d.facial_rec_tag[0]
            # Draw a box around the face
            cv2.rectangle(img, (left - 20, top - 20), (right + 20, bottom + 20), (255, 0, 0), 2)
            # Draw a label with a name below the face
            cv2.rectangle(
                img, (left - 20, bottom - 15), (right + 20, bottom + 20), (255, 0, 0), cv2.FILLED
            )
            font = cv2.FONT_HERSHEY_DUPLEX
            cv2.putText(img, name, (left - 20, bottom + 15), font, 1.0, (255, 255, 255), 2)

        cv2.namedWindow("faces", cv2.WINDOW_NORMAL)  # Create window with freedom of dimensions
        img = cv2.resize(img, (2024, 1960))  # Resize image
        img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        cv2.imshow("faces", img)
        cv2.waitKey(3)
