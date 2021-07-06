"""
Copyright (c) Facebook, Inc. and its affiliates.
"""

import logging
import datetime
from typing import Tuple, Dict, Any, Optional
from droidlet.event import dispatch

# FIXME agent
from droidlet.dialog.dialogue_objects import DialogueObject, ConfirmTask
from .interpreter_utils import SPEAKERLOOK

# point target should be subinterpret, dance should be in agents subclassed interpreters
from .reference_object_helpers import ReferenceObjectInterpreter, interpret_reference_object
from .location_helpers import ReferenceLocationInterpreter, interpret_relative_direction
from .filter_helper import FilterInterpreter

from ..shared_data_structs import ErrorWithResponse, NextDialogueStep
from droidlet.interpreter.task import maybe_task_list_to_control_block
from droidlet.memory.memory_nodes import TripleNode, TaskNode


class Interpreter(DialogueObject):
    """
    | This class processes incoming chats and modifies the task stack.
    | Handlers should add/remove/reorder tasks on the stack, but not execute them.
    | Most of the logic of the interpreter is run in the subinterpreters or task handlers.
    | The keyword args in __init__ match the base DialogueObject class

    Args:
        speaker: The name of the player/human/agent who uttered the chat resulting in this interpreter
        action_dict: The logical form, e.g. returned by a semantic parser

    Keyword Args:
        agent: the agent running this Interpreter
        memory: the agent's memory
        dialogue_stack: a DialogueStack object where this Interpreter object will live
    """
    def __init__(self, speaker: str, action_dict: Dict, low_level_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.speaker = speaker
        self.action_dict = action_dict
        self.provisional: Dict = {}
        self.action_dict_frozen = False
        self.loop_data = None
        self.archived_loop_data = None
        self.default_debug_path = "debug_interpreter.txt"
        self.post_process_loc = lambda loc, interpreter: loc

        # make sure to do in subclass
        # this is the order of things to search in workspace memory if a ref object
        # is not found, FIXME! (use more sophisticated search):
        self.workspace_memory_prio = []  # noqa

        # reorganize by signature?
        # e.g.
        #  logical_form --> list(mems)
        #  logical_form, list(mems) --> list(mems)
        #  logical_form, list(mems), list(vals) --> list(mems), list(vals)
        self.subinterpret = {
            "filters": FilterInterpreter(),
            # FIXME, just make a class
            "reference_objects": ReferenceObjectInterpreter(interpret_reference_object),
            "reference_locations": ReferenceLocationInterpreter(),
            # make sure to do this in sfubclass
            # "attribute": MCAttributeInterpreter(),
            # "condition": ConditionInterpreter(),
            # "specify_locations": ComputeLocations(),
            # "facing": FacingInterpreter(),
        }

        # each action handler should have signature
        # speaker, logical_form -->  a Task, possible output utterance, possible output data.
        #     if the action handler builds a list, it should wrap it in a ControlBlock
        self.action_handlers = {
            "MOVE": self.handle_move,
            "STOP": self.handle_stop,
            "RESUME": self.handle_resume,
            "UNDO": self.handle_undo,
            "OTHERACTION": self.handle_otheraction,
        }

        # fill these in subclasses
        self.task_objects = {}  # noqa

    def step(self, agent) -> Tuple[Optional[str], Any]:
        start_time = datetime.datetime.now()
        assert self.action_dict["dialogue_type"] == "HUMAN_GIVE_COMMAND"
        try:
            actions = []
            if "action" in self.action_dict:
                actions.append(self.action_dict["action"])
            elif "action_sequence" in self.action_dict:
                actions = self.action_dict["action_sequence"]

            if len(actions) == 0:
                # The action dict is in an unexpected state
                raise ErrorWithResponse(
                    "I thought you wanted me to do something, but now I don't know what"
                )
            tasks_to_push = []
            for action_def in actions:
                action_type = action_def["action_type"]
                r = self.action_handlers[action_type](agent, self.speaker, action_def)
                if len(r) == 3:
                    task, response, dialogue_data = r
                else:
                    # FIXME don't use this branch, uniformize the signatures
                    task = None
                    response, dialogue_data = r
                if task:
                    tasks_to_push.append(task)
            task_mem = None
            if tasks_to_push:
                T = maybe_task_list_to_control_block(tasks_to_push, agent)
                task_mem = TaskNode(self.memory, tasks_to_push[0].memid)
            if task_mem:
                chat = self.memory.get_most_recent_incoming_chat()
                TripleNode.create(
                    self.memory, subj=chat.memid, pred_text="chat_effect_", obj=task_mem.memid
                )
            self.finished = True
            end_time = datetime.datetime.now()
            hook_data = {
                "name" : "interpreter",
                "start_datetime" : start_time,
                "end_datetime" : end_time,
                "agent_time" : self.memory.get_time(),
                "tasks_to_push" : tasks_to_push,
                "task_mem" : task_mem,
            }
            dispatch.send("interpreter", data=hook_data)
            return response, dialogue_data
        except NextDialogueStep:
            return None, None
        except ErrorWithResponse as err:
            self.finished = True
            return err.chat, None

    def handle_undo(self, agent, speaker, d) -> Tuple[Optional[str], Any]:
        Undo = self.task_objects["undo"]
        task_name = d.get("undo_action")
        if task_name:
            task_name = task_name.split("_")[0].strip()
        old_task = self.memory.get_last_finished_root_task(task_name)
        if old_task is None:
            raise ErrorWithResponse("Nothing to be undone ...")
        undo_tasks = [Undo(agent, {"memid": old_task.memid})]
        undo_command = old_task.get_chat().chat_text

        logging.debug("Pushing ConfirmTask tasks={}".format(undo_tasks))
        # FIXME agent
        self.memory.dialogue_stack_append_new(
            ConfirmTask,
            'Do you want me to undo the command: "{}" ?'.format(undo_command),
            undo_tasks,
        )
        self.finished = True
        return None, None

    def handle_move(self, agent, speaker, d) -> Tuple[Optional[str], Any]:
        Move = self.task_objects["move"]
        Control = self.task_objects["control"]

        def new_tasks():
            # TODO if we do this better will be able to handle "stay between the x"
            default_loc = getattr(self, "default_loc", SPEAKERLOOK)
            location_d = d.get("location", default_loc)
            # FIXME! this loop_data trick can now be done more properly with
            # a fixed mem filter
            if self.loop_data and hasattr(self.loop_data, "get_pos"):
                mems = [self.loop_data]
            else:
                mems = self.subinterpret["reference_locations"](self, speaker, location_d)
            # FIXME this should go in the ref_location subinterpret:
            steps, reldir = interpret_relative_direction(self, location_d)
            pos, _ = self.subinterpret["specify_locations"](self, speaker, mems, steps, reldir)
            # TODO: can this actually happen?
            if pos is None:
                raise ErrorWithResponse("I don't understand where you want me to move.")
            pos = self.post_process_loc(pos, self)
            task_data = {"target": pos, "action_dict": d}
            task = Move(agent, task_data)
            return task

        if "remove_condition" in d:
            condition = self.subinterpret["condition"](self, speaker, d["stop_condition"])
            location_d = d.get("location", SPEAKERLOOK)
            mems = self.subinterpret["reference_locations"](self, speaker, location_d)
            if mems:
                self.loop_data = mems[0]
            steps, reldir = interpret_relative_direction(self, location_d)

            # FIXME grammar to handle "remove" vs "stop"
            loop_task_data = {
                "new_tasks": new_tasks,
                "remove_condition": condition,  #!!! semantic parser + GT need updating
                "action_dict": d,
            }
            return Control(agent, loop_task_data), None, None
        else:
            return new_tasks(), None, None

    # TODO mark in memory it was stopped by command
    def handle_stop(self, agent, speaker, d) -> Tuple[Optional[str], Any]:
        self.finished = True
        if self.loop_data is not None:
            # TODO if we want to be able stop and resume old tasks, will need to store
            self.archived_loop_data = self.loop_data
            self.loop_data = None
        if self.memory.task_stack_pause():
            return None, "Stopping.  What should I do next?", None
        else:
            return None, "I am not doing anything", None

    # FIXME this is needs updating...
    # TODO mark in memory it was resumed by command
    def handle_resume(self, agent, speaker, d) -> Tuple[Optional[str], Any]:
        self.finished = True
        if self.memory.task_stack_resume():
            if self.archived_loop_data is not None:
                # TODO if we want to be able stop and resume old tasks, will need to store
                self.loop_data = self.archived_loop_data
                self.archived_loop_data = None
            return None, "resuming", None
        else:
            return None, "nothing to resume", None

    def handle_otheraction(self, agent, speaker, d) -> Tuple[Optional[str], Any]:
        self.finished = True
        return None, "I don't know how to do that yet", None
