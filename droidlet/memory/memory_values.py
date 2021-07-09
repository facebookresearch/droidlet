"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
# FIXME!! torch this whole file, replace with filters
from .memory_filters import MemorySearcher
from droidlet.base_util import TICKS_PER_SEC, TICKS_PER_MINUTE, TICKS_PER_HOUR


# a value has a get_value() method; and get_value should not have
# any inputs
class ComparisonValue:
    def __init__(self, memory):
        self.memory = memory

    def get_value(self):
        raise NotImplementedError("Implemented by subclass")


# TODO more composable less ugly, more ML friendly
class ScaledValue(ComparisonValue):
    def __init__(self, value, scale):
        self.value = value
        self.scale = scale

    def get_value(self):
        return self.scale * self.value.get_value()


# TODO feet, meters, inches, centimeters, degrees, etc.
# each of these converts a measure into the agents internal units,
#     e.g. seconds/minutes/hours to ticks
#     inches/centimeters/feet to meters or blocks (assume 1 block in mc equals 1 meter in real world)
CONVERSION_FACTORS = {
    "seconds": TICKS_PER_SEC,
    "minutes": TICKS_PER_MINUTE,
    "hours": TICKS_PER_HOUR,
}


def convert_comparison_value(comparison_value, unit):
    if not unit:
        return comparison_value
    assert CONVERSION_FACTORS.get(unit)
    return ScaledValue(comparison_value, CONVERSION_FACTORS[unit])


class FixedValue(ComparisonValue):
    def __init__(self, memory, value):
        super().__init__(memory)
        self.value = value

    def get_value(self):
        return self.value


# TODO store more in memory,
# or at least
# make some TimeNodes as side effects
# WARNING:  elapsed mode uses get_time at construction as 0
class TimeValue(ComparisonValue):
    """
    modes are elapsed, time, and world_time.
    if "elapsed" or "time" uses memory.get_time as timer
    if "elapsed", value is offset by time at creation
    if "world_time" uses memory.get_world_time
    """

    def __init__(self, memory, mode="elapsed"):
        self.mode = mode
        self.offset = 0.0
        if self.mode == "elapsed":
            self.offset = memory.get_time()
            self.get_time = memory.get_time
        elif self.mode == "time":
            self.get_time = memory.get_time
        else:  # world_time
            self.get_time = memory.get_world_time

    def get_value(self):
        return self.get_time() - self.offset


# FIXME!!: just use FilterValue
class LinearExtentValue(ComparisonValue):
    # this is a linear extent with both source and destination filled.
    # e.g. "when you are as far from the house as the cow is from the house"
    # but NOT for "when the cow is 3 steps from the house"
    # in the latter case, one of the two entities will be given by the filters
    def __init__(self, memory, linear_exent_attribute, mem=None, query=""):
        super().__init__(memory)
        self.linear_extent_attribute = linear_exent_attribute
        assert mem or query
        self.searcher = None
        self.mem = mem
        # FIXME!!! put FILTERS here
        if not self.mem:
            self.searcher = MemorySearcher(query=query)

    def get_value(self):
        if self.mem:
            mems = [self.mem]
        else:
            _, mems = self.searcher.search(self.memory)
        if len(mems) > 0:
            # TODO/FIXME! deal with more than 1 better
            return self.linear_extent_attribute(mems)[0]
        else:
            return


# TODO unit conversions?
# TODO/FIXME! check that the memory_filter outputs a single memid/value pair
class FilterValue(ComparisonValue):
    def __init__(self, memory, memory_filter):
        super().__init__(memory)
        self.memory_filter = memory_filter

    def get_value(self):
        _, vals = self.memory_filter()
        return vals[0]
