"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from droidlet.interpreter.condition import (
    TaskStatusCondition,
    SwitchCondition,
    AndCondition,
)
from droidlet.memory.memory_nodes import TaskNode, LocationNode, TripleNode

# FIXME TODO store conditions in memory (new table)
# TaskNode method to update a tasks conditions
# dsl/put_memory for commands to do so
from droidlet.shared_data_structs import Task


# put a counter and a max_count so can't get stuck?


class TaskListWrapper:
    """gadget for converting a list of tasks into a callable that serves as a new_tasks
        callable for a ControlBlock.

    Args:
        agent: the agent who will perform the task list

    Attributes:
        append:  append a task to the list; set the init_condition of the task to be
                 appended to be its current init_condition and that the previous task
                 in the list is completed (assuming there is a previous task).  if this
                 the first task to be appended to the list, instead is ANDed with a
                 SwitchCondition to be triggered by the ControlBlock enclosing this
        __call__: the call outputs the next Task in the list
    """

    def __init__(self, agent):
        self.task_list = []
        self.task_list_idx = 0
        self.prev = None
        self.agent = agent

    def append(self, task):
        if self.prev is not None:
            prev_finished = TaskStatusCondition(self.agent, self.prev.memid, status="finished")
            cdict = {
                "init_condition": AndCondition(self.agent, [task.init_condition, prev_finished])
            }
            TaskNode(self.agent.memory, task.memid).update_condition(cdict)
        else:
            self.fuse = SwitchCondition(self.agent)
            cdict = {"init_condition": AndCondition(self.agent, [task.init_condition, self.fuse])}
            TaskNode(self.agent.memory, task.memid).update_condition(cdict)
            self.fuse.set_status(False)
        self.prev = task
        self.task_list.append(task)

    def __call__(self):
        if self.task_list_idx >= len(self.task_list):
            return None
        task = self.task_list[self.task_list_idx]
        self.task_list_idx += 1
        return task


# if you want a list of tasks, have to enclose in a ControlBlock
# if you want to loop over a list of tasks, you need a tasks_fn that
# generates a ControlBlock C = tasks_fn() wrapping the (newly_generated) list,
# and another D that encloses C, that checkes the remove and stop conditions.
#
# FIXME/TODO: name any nonpicklable attributes in the object
class ControlBlock(Task):
    """Container for task control

    Args:
        agent: the agent who will perform this task
        task_data (dict): a dictionary stores all task related data
            task_data["new_tasks"] is a callable, when called it returns a Task or None
            when it returns None, this ControlBlock is finished.
            to make an infinite loop, the callable needs to keep returning Tasks;
    """

    def __init__(self, agent, task_data):
        super().__init__(agent, task_data=task_data)
        self.tasks_fn = task_data.get("new_tasks")
        if hasattr(self.tasks_fn, "fuse"):
            self.tasks_fn.fuse.set_status(True)
        TaskNode(self.agent.memory, self.memid).update_task(task=self)

    @Task.step_wrapper
    def step(self):
        t = self.tasks_fn()
        if t is not None:
            self.add_child_task(t, prio=None)
            self.run_count += 1
        else:
            self.finished = True


class BaseMovementTask(Task):
    """a Task that changes the location of the agent

    Args:
        agent: the agent who will perform this task
        task_data (dict): a dictionary stores all task related data
            task_data should have a key "target" with a target location

    Attributes:
        target_to_memory:  method that converts the task_data target into a location to record in memory

    """

    # TODO FIXME!  PoseNode instead of LocationNode
    # TODO put ref object info here?
    def __init__(self, agent, task_data):
        super().__init__(agent)
        assert task_data.get("target") is not None
        loc = self.target_to_memory(task_data["target"])
        loc_memid = LocationNode.create(agent.memory, loc)
        TripleNode.create(
            agent.memory, subj=self.memid, pred_text="task_reference_object", obj=loc_memid
        )

    def target_to_memory(self, target):
        raise NotImplementedError


def maybe_task_list_to_control_block(maybe_task_list, agent):
    """
    if input is a list of tasks with len > 1, outputs a ControlBlock wrapping them
    if it is a list of tasks with len = 1, returns that task

    Args:
        maybe_task_list:  could be a list of Task objects or a Task object
        agent: the agent that will carry out the tasks

    Returns: a Task.  either the single input Task or a ControlBlock wrapping them if
             there are more than one
    """

    if len(maybe_task_list) == 1:
        return maybe_task_list[0]
    if type(maybe_task_list) is not list:
        return maybe_task_list
    W = TaskListWrapper(agent)
    for t in maybe_task_list:
        W.append(t)
    return ControlBlock(agent, {"new_tasks": W})
