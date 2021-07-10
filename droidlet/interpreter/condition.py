"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from droidlet.memory.memory_attributes import COMPARATOR_FUNCTIONS
from droidlet.memory.memory_values import TimeValue


class Condition:
    def __init__(self, memory):
        self.memory = memory

    def check(self) -> bool:
        raise NotImplementedError("Implemented by subclass")


class SwitchCondition(Condition):
    def __init__(self, memory):
        super().__init__(memory)
        self.name = "switch"
        self.status = True

    def set_status(self, status):
        self.status = status

    def check(self):
        return self.status


class NeverCondition(Condition):
    def __init__(self, memory):
        super().__init__(memory)
        self.name = "never"

    def check(self):
        return False


class AlwaysCondition(Condition):
    def __init__(self, memory):
        super().__init__(memory)
        self.name = "always"

    def check(self):
        return True


class NotCondition(Condition):
    def __init__(self, memory, condition):
        super().__init__(memory)
        self.name = "not"
        self.condition = condition

    def check(self):
        c = not self.condition.check()
        return c


class AndCondition(Condition):
    """conditions should be an iterable"""

    def __init__(self, memory, conditions):
        super().__init__(memory)
        self.name = "and"
        self.conditions = conditions

    def check(self):
        for c in self.conditions:
            if not c.check():
                return False
        return True


class OrCondition(Condition):
    """conditions should be an iterable"""

    def __init__(self, memory, conditions):
        super().__init__(memory)
        self.name = "or"
        self.conditions = conditions

    def check(self):
        for c in self.conditions:
            if c.check():
                return True
        return False


class TaskStatusCondition(Condition):
    def __init__(self, memory, task_memid, status="finished"):
        super().__init__(memory)
        self.status = status
        self.task_memid = task_memid

    def check(self):
        T = None
        if self.memory.check_memid_exists(self.task_memid, "Tasks"):
            T = self.memory.get_mem_by_id(self.task_memid)
        if self.status == "finished":
            # beware:
            # assumption is if we had the memid in hand, and it is no longer a task, task is finished
            # if (e.g. via a bug) a non-task memid is passed here, it will be considered a finished task.
            if (not T) or T.finished > -1:
                return True
        elif self.status == "running":
            if T and T.running > 0:
                return True
        elif self.status == "paused":
            if T and T.paused > 0:
                return True
        else:
            raise AssertionError("TaskStatusCondition has unkwon status {}".format(self.status))
        return False


# start_time and end_time are in (0, 1)
# 0 is sunrise, .5 is sunset
def build_special_time_condition(memory, start_time, end_time, epsilon=0.01):
    value_left = TimeValue(memory, mode="world_time")
    if end_time > 0:
        start = Comparator(
            comparison_type="GREATER_THAN_EQUAL", value_left=value_left, value_right=start_time
        )
        end = Comparator(
            comparison_type="LESS_THAN_EQUAL", value_left=value_left, value_right=end_time
        )
        return AndCondition(memory, [start, end])
    else:
        return Comparator(
            comparison_type="CLOSE_TO",
            value_left=value_left,
            value_right=start_time,
            epsilon=epsilon,
        )


# TODO make this more ML friendly?
# eventually do "x minutes before condition"?  how?
# KEEPS state (did the event occur- starts timer then)
class TimeCondition(Condition):
    """
    if event is None, the timer starts now
    if event is not None, it should be a condition, timer starts on the condition being true
    This time condition is true when the comparator between
    timer (as value_left) and the comparator's value_right is true
    if comparator is a string, it should be "SUNSET" / "SUNRISE" / "DAY" / "NIGHT" / "AFTERNOON" / "MORNING"
    else it should be built in the parent, and the value_right should be commeasurable (properly scaled)
    """

    def __init__(self, memory, comparator, event=None):
        super().__init__(memory)
        self.special = None
        self.event = event
        if type(comparator) is str:
            if comparator == "SUNSET":
                self.special = build_special_time_condition(memory, 0.5, -1)
            elif comparator == "SUNRISE":
                self.special = build_special_time_condition(memory, 0.0, -1)
            elif comparator == "MORNING":
                self.special = build_special_time_condition(memory, 0, 0.25)
            elif comparator == "AFTERNOON":
                self.special = build_special_time_condition(memory, 0.25, 0.5)
            elif comparator == "DAY":
                self.special = build_special_time_condition(memory, 0.0, 0.5)
            elif comparator == "NIGHT":
                self.special = build_special_time_condition(memory, 0.5, 1.0)
            else:
                raise NotImplementedError("unknown special time condition type: " + comparator)
        else:
            if not event:
                comparator.value_left = TimeValue(memory, mode="elapsed")
            self.comparator = comparator

    def check(self):
        if not self.event:
            return self.comparator.check()
        else:
            if self.event.check():
                self.comparator.value_left = TimeValue(self.memory, mode="elapsed")
                self.event = None
            return self.comparator.check()


class Comparator(Condition):
    def __init__(
        self, memory, comparison_type="EQUAL", value_left=None, value_right=None, epsilon=0
    ):
        super().__init__(memory)
        self.comparison_type = comparison_type
        self.value_left = value_left
        self.value_right = value_right
        self.epsilon = epsilon

    # raise errors if no value left or right?
    # raise errors if strings compared with > < etc.?
    # FIXME handle type mismatches
    # TODO less types, use NotCondition
    # TODO MOD_EQUAL, MOD_CLOSE
    def check(self):
        value_left = self.value_left.get_value()
        value_right = self.value_right.get_value()
        if not self.value_left:
            return False
        if not value_right:
            return False
        f = COMPARATOR_FUNCTIONS.get(self.comparison_type)
        if f:
            return f(value_left, value_right, self.epsilon)
        else:
            raise Exception("unknown comparison type {}".format(self.comparison_type))
