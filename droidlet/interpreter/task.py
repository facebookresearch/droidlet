"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from droidlet.interpreter.condition import (
    AlwaysCondition,
    NeverCondition,
    NotCondition,
    TaskStatusCondition,
    SwitchCondition,
    AndCondition,
)
from droidlet.memory.memory_nodes import TaskNode, LocationNode, TripleNode

# FIXME TODO store conditions in memory (new table)
# TaskNode method to update a tasks conditions
# dsl/put_memory for commands to do so

# FIXME agent, move this to a better place
# from droidlet.shared_data_structs import Task


def maybe_update_condition_memid(condition, memid, pos="value_left"):
    if hasattr(condition, pos):
        v = getattr(condition, pos)
        if hasattr(v, "memory_filter"):
            if hasattr(v.memory_filter.head, "memid"):
                if v.memory_filter.head.memid == "NULL":
                    # this was a special "THIS" filter condition, needed to wait till here
                    # to get memid
                    v.memory_filter.head.memid = memid


class Task(object):
    """This class represents a Task, the exact implementation of which
    will depend on the framework and environment. A task can be placed on a
    task stack, and represents a unit (which in itself can contain a sequence of s
    smaller subtasks).

    Attributes:
        memid (string): Memory id of the task in agent's memory
        interrupted (bool): A flag indicating whetherr the task has been interrupted
        finished (bool): A flag indicating whether the task finished
        name (string): Name of the task
        undone (bool): A flag indicating whether the task was undone / reverted
        last_stepped_time (int): Timestamp of last step through the task
        stop_condition (Condition): The condition on which the task will be stopped (by default,
                        this is NeverCondition)
    Examples::
        >>> Task()
    """

    def __init__(self, agent, task_data={}):
        self.agent = agent
        self.run_count = 0
        self.interrupted = False
        self.finished = False
        self.name = None
        self.undone = False
        self.last_stepped_time = None
        self.prio = -1
        self.running = 0
        self.memid = TaskNode.create(self.agent.memory, self)
        # TODO put these in memory in a new table?
        # TODO methods for safely changing these
        i, s, ru, re = self.get_default_conditions(task_data, agent)
        self.init_condition = i
        self.stop_condition = s
        self.run_condition = ru
        self.remove_condition = re
        TripleNode.create(
            self.agent.memory,
            subj=self.memid,
            pred_text="has_name",
            obj_text=self.__class__.__name__.lower(),
        )
        TaskNode(agent.memory, self.memid).update_task(task=self)
        # TODO if this is a command, put a chat_effect triple

    @staticmethod
    def step_wrapper(stepfn):
        def modified_step(self):
            if self.remove_condition.check():
                self.finished = True
            if self.finished:
                TaskNode(self.agent.memory, self.memid).get_update_status(
                    {"prio": -2, "finished": True}
                )
                return
            query = "SELECT MEMORY FROM Task WHERE ((prio>=1) AND (_has_parent_task=#={}))".format(
                self.memid
            )
            _, child_task_mems = self.agent.memory.basic_search(query)
            if child_task_mems:  # this task has active children, step them
                return
            r = stepfn(self)
            TaskNode(self.agent.memory, self.memid).update_task(task=self)
            return

        return modified_step

    def step(self):
        """The actual execution of a single step of the task is defined here."""
        pass

    def get_default_conditions(self, task_data, agent):
        """
        takes a task_data dict and fills in missing conditions with defaults

        Args:
            task_data (dict):  this function will try to use the values of "init_condition",
                               "stop_condition", "run_condition", and "remove_condition"
            agent (Droidlet Agent): the agent that is going to be doing the Task controlled by
                                    condition
            task (droidlet.shared_data_structs.Task):  the task to be controlled by the conditions
        """
        init_condition = task_data.get("init_condition", AlwaysCondition(None))

        run_condition = task_data.get("run_condition")
        stop_condition = task_data.get("stop_condition")
        if stop_condition is None:
            if run_condition is None:
                stop_condition = NeverCondition(None)
                run_condition = AlwaysCondition(None)
            else:
                stop_condition = NotCondition(run_condition)
        elif run_condition is None:
            run_condition = NotCondition(stop_condition)

        remove_condition = task_data.get(
            "remove_condition", TaskStatusCondition(agent.memory, self.memid)
        )
        # check/maybe update if special "THIS" filter condition
        # FIXME do this for init, run, etc.
        maybe_update_condition_memid(remove_condition, self.memid)

        return init_condition, stop_condition, run_condition, remove_condition

    # FIXME remove all this its dead now...
    def interrupt(self):
        """Interrupt the task and set the flag"""
        self.interrupted = True

    def check_finished(self):
        """Check if the task has marked itself finished

        Returns:
            bool: If the task has finished
        """
        if self.finished:
            return self.finished

    def add_child_task(self, t, prio=1):
        TaskNode(self.agent.memory, self.memid).add_child_task(t, prio=prio)

    def __repr__(self):
        return str(type(self))


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
            prev_finished = TaskStatusCondition(
                self.agent.memory, self.prev.memid, status="finished"
            )
            cdict = {
                "init_condition": AndCondition(
                    self.agent.memory, [task.init_condition, prev_finished]
                )
            }
            TaskNode(self.agent.memory, task.memid).update_condition(cdict)
        else:
            self.fuse = SwitchCondition(self.agent.memory)
            cdict = {
                "init_condition": AndCondition(self.agent.memory, [task.init_condition, self.fuse])
            }
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
