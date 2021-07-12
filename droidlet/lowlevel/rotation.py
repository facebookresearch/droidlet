"""
Copyright (c) Facebook, Inc. and its affiliates.
"""

import numpy as np
from numpy import sin, cos

DIRECTIONS = {
    "AWAY": np.array([0, 0, 1]),
    "FRONT": np.array([0, 0, 1]),
    "BACK": np.array([0, 0, -1]),
    "LEFT": np.array([-1, 0, 0]),
    "RIGHT": np.array([1, 0, 0]),
    "DOWN": np.array([0, -1, 0]),
    "UP": np.array([0, 1, 0]),
}

# FIXME add the xz_only option for mc also, shouldn't use yaw for determining "up"
def transform(direction, yaw, pitch, inverted=False, xz_only=False):
    """Coordinate transforms with respect to yaw/pitch of the viewer direction
    should be relative to the viewer *before* pitch/yaw transform If we want to
    transform any of DIRECTIONS back, then it would be inverted=True that is:
    inverted=True finds the vector in canonical coords pointing towards
    direction where direction is specified if you were facing yaw, pitch.

    conversely, inverted=False takes a direction in canonical
    coordinates and converts to coordinates where FRONT (z+) is yaw=0
    and pitch=0 yaw is assumed to be in the range [-pi, pi], and
    increasing yaw moves *counterclockwise* pitch is assumed to be in
    the range [-pi/2, pi/2].  pi/2 is down, -pi/2 is up.
    """

    # 0 yaw is z axis
    #                 z+
    #           +yaw  |  -yaw
    #                 |
    #                 |
    #                 |
    #    x-___________|___________x+
    #                 |
    #                 |
    #                 z-

    # fmt: off
    ryaw = np.array([[cos(yaw), 0,   -sin(yaw)],
                   [0,          1,    0       ],
                   [sin(yaw),   0,    cos(yaw)]])

    rpitch = np.array([[1,   0,             0          ],
                       [0,   cos(-pitch),   sin(-pitch)],
                       [0,   -sin(-pitch),  cos(-pitch)]])

    # fmt: on

    # canonical world coords:
    #         ^ y+
    #         |     z+
    #         |   /
    #         | /
    #         0 -----> x+
    if not inverted:
        trans_mat = rpitch @ ryaw
    else:
        trans_mat = np.linalg.inv(rpitch @ ryaw)
    return trans_mat @ direction


def yaw_pitch(look_vec):
    xz_dir = np.array([look_vec[0], look_vec[2]])
    xz_dir = xz_dir / np.linalg.norm(xz_dir)
    yaw = np.arctan2(-xz_dir[0], xz_dir[1])

    # get the pitch value/tilt angle
    pitch = -np.arctan2(look_vec[1], np.sqrt(look_vec[0] ** 2 + look_vec[2] ** 2))

    yaw = yaw % (2 * np.pi)
    if yaw > np.pi:
        yaw = yaw - 2 * np.pi
    return yaw, pitch


# this should invert yaw_pitch (up to norm)
def look_vec(yaw, pitch):
    #    yaw = deg2rad(yaw)
    #    pitch = deg2rad(pitch)
    x = -cos(pitch) * sin(yaw)
    y = sin(pitch)
    z = cos(pitch) * cos(yaw)
    return np.array([x, y, z])


if __name__ == "__main__":
    A = (4, 0, 1)
    B = (4, 4, 4)
    print(transform(DIRECTIONS["RIGHT"], 45, 0, inverted=True))
    print("yaw_pitch(look_vec(3.1, -1.0))")
    print(yaw_pitch(look_vec(3.1, -1.0)))
    print("look_vec(*yaw_pitch(np.array((-2,1,1))))")
    print(look_vec(*yaw_pitch(np.array((-2, 1, 1)))))
