"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import numpy as np
from droidlet.lowlevel.rotation import look_vec
import random


HUMAN_NAMES = ["sara", "mary", "arthur", "anurag", "soumith"]


class Opt:
    pass


def is_close_direction(x, y, tol):
    x = x / np.linalg.norm(x)
    y = y / np.linalg.norm(y)
    if x @ y > tol:
        return True
    return False


def check_bounds(p, sl):
    if p >= sl or p < 0:
        return -1
    return 1


def make_human_opts():
    opts = Opt()
    opts.name = random.choice(HUMAN_NAMES)
    opts.direction_change_prob = 0.1
    opts.speed = 0.1
    opts.loiter_prob = 0.1
    opts.loiter_time = 1
    return opts


# TODO extent
class SimpleHuman:
    def __init__(self, opts, start_pos=None, start_look=(0.0, 0.0)):
        self.direction_change_prob = opts.direction_change_prob
        self.name = opts.name
        self.loiter_prob = opts.loiter_prob
        self.loiter_time = opts.loiter_time
        self.speed = opts.speed
        self.pos = start_pos  # tuple
        # TODO update these
        self.pitch = start_look[0]
        self.yaw = start_look[1]
        self.loiter_time = -1
        self.new_direction()

    def add_to_world(self, world):
        self.world = world
        if self.pos is None:
            xz = np.random.randint(0, world.sl, (2,))
            # position of head
            self.pos = (float(xz[0]), 2.0, float(xz[1]))
        self.world.players.append(self)

    def get_info(self):
        info = {}
        info["pos"] = self.pos
        info["pitch"] = self.pitch
        info["yaw"] = self.yaw
        info["name"] = self.name
        # FIXME!
        info["eid"] = self.name
        return info

    def new_direction(self):
        new_direction = np.random.randn(2)
        self.direction = new_direction / np.linalg.norm(new_direction)
        # self.look ##NOT IMPLEMENTED

    def step(self):
        # TODO don't colocate with objects
        x, y, z = self.pos
        # TODO when look implemented: change looks when loitering
        if self.loiter_time >= 0:
            self.loiter_time += 1
            if self.loiter_time > self.loiter_time:
                self.loiter_time = -1
            return
        if np.random.rand() < self.loiter_prob:
            self.loiter_time = 0
            return
        if np.random.rand() < self.direction_change_prob:
            self.new_direction()
        step = self.direction * self.speed
        bx = check_bounds(int(np.round(x + step[0])), self.world.sl)
        bz = check_bounds(int(np.round(z + step[1])), self.world.sl)
        # if hitting boundary, reverse...
        self.direction[0] = bx * self.direction[0]
        self.direction[1] = bz * self.direction[1]
        step = self.direction * self.speed
        new_x = step[0] + x
        new_z = step[1] + z
        # TODO is there an object in new location? if no go there,
        self.pos = (new_x, 0, new_z)
        return


class World:
    # world is a 2*opts.sl box
    def __init__(self, opts, spec):
        self.opts = opts
        self.count = 0
        self.sl = opts.sl

        self.players = []
        for p in spec["players"]:
            p.add_to_world(self)
        self.agent_data = spec["agent"]
        self.chat_log = []
        self.objects = []

    def step(self):
        for m in self.players:
            m.step()
        for obj in self.objects:
            a = obj.get("attached")
            if a is not None:
                obj["pos"][0] = a.pos[0]
                obj["pos"][1] = 1.0
                obj["pos"][2] = a.pos[1]
        self.count += 1

    def get_object_info(self, obj):
        return {k: obj[k] for k in obj if k != "attached"}

    # TODO fix objects etc.
    def get_info(self):
        info = {}
        info["agent"] = self.agent.get_info()
        info["humans"] = self.get_other_players()
        info["objects"] = [self.get_object_info(o) for o in self.objects]
        return info

    # TODO make objects less hacky
    def add_object(self, xyz, tags=[], colour=None):
        self.objects.append({"pos": xyz, "tags": tags, "colour": colour, "attached": None})

    def attach_object_to_agent(self, obj, agent):
        obj["attached"] = agent

    def detach_object_from_agent(self, obj):
        obj["attached"] = None
        obj["pos"][1] = 0.0  # it gets put on the floor, TODO one thing on top of another

    def get_other_players(self):
        return [p.get_info() for p in self.players]

    def get_line_of_sight(self, pos, yaw, pitch):
        tol = 0.8
        # it is assumed lv is unit normalized
        lv = look_vec(yaw, pitch)
        pos = np.array(pos)
        # does the ray intersect a player or object:
        intersected = []
        for p in self.players:
            if is_close_direction(np.array(p.pos) - pos, lv, tol):
                intersected.append(p.pos)
        for o in self.objects:
            if is_close_direction(np.array(o["pos"]) - pos, lv, tol):
                intersected.append(o["pos"])
        if len(intersected) > 0:
            intersected.sort(key=lambda x: np.linalg.norm(np.array(x) - pos))
            return intersected[0]

        wall_hits = []
        for coord in range(3):
            s = np.sign(lv[coord])
            ep = (self.sl - s * pos[coord]) / (s * lv[coord] + 0.00001)
            hit = pos + ep * lv
            wall_hits.append((ep, hit))
        closest_hit = min(wall_hits, key=lambda x: x[0])
        return closest_hit[1]

    def add_incoming_chat(self, chat: str, speaker_name: str):
        """Add a chat to memory as if it was just spoken by SPEAKER."""
        self.chat_log.append("<" + speaker_name + ">" + " " + chat)
