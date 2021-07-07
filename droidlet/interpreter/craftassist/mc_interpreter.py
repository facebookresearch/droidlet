"""
Copyright (c) Facebook, Inc. and its affiliates.
"""

import logging
import numpy as np
import random
from droidlet.perception.craftassist import heuristic_perception
from typing import Tuple, Dict, Any, Optional
from copy import deepcopy
from word2number.w2n import word_to_num

from droidlet.dialog.dialogue_objects import Say

from droidlet.interpreter import (
    Interpreter,
    SPEAKERLOOK,
    interpret_relative_direction,
    get_repeat_num,
    filter_by_sublocation,
    interpret_dance_filter,
    convert_location_to_selector,
)

from .schematic_helper import (
    get_repeat_dir,
    interpret_schematic,
    interpret_size,
    interpret_fill_schematic,
)

from .facing_helper import FacingInterpreter

from .modify_helpers import (
    handle_fill,
    handle_rigidmotion,
    handle_scale,
    handle_replace,
    handle_thicken,
)
from .spatial_reasoning import ComputeLocations
from ..condition_helper import ConditionInterpreter
from .attribute_helper import MCAttributeInterpreter
from .point_target import PointTargetInterpreter
from droidlet.base_util import number_from_span
from droidlet.shared_data_structs import ErrorWithResponse
from droidlet.memory.memory_nodes import PlayerNode
from droidlet.memory.craftassist.mc_memory_nodes import MobNode, ItemStackNode
from droidlet.interpreter.craftassist import tasks, dance
from droidlet.interpreter.task import ControlBlock, maybe_task_list_to_control_block


class MCInterpreter(Interpreter):
    """This class handles processes incoming chats and modifies the task stack

    Handlers should add/remove/reorder tasks on the stack, but not execute them.
    """

    def __init__(self, speaker: str, action_dict: Dict, low_level_data: Dict = None, **kwargs):
        super().__init__(speaker, action_dict, **kwargs)
        self.default_frame = "SPEAKER"
        self.block_data = low_level_data["block_data"]
        self.special_shape_functions = low_level_data["special_shape_functions"]
        self.workspace_memory_prio = ["Mob", "BlockObject"]
        self.subinterpret["attribute"] = MCAttributeInterpreter()
        self.subinterpret["condition"] = ConditionInterpreter()
        self.subinterpret["specify_locations"] = ComputeLocations()
        self.subinterpret["facing"] = FacingInterpreter()
        self.subinterpret["dances_filters"] = interpret_dance_filter
        self.subinterpret["point_target"] = PointTargetInterpreter()

        # logical_form --> possible task placed on stack + side effects
        self.action_handlers["BUILD"] = self.handle_build
        self.action_handlers["DESTROY"] = self.handle_destroy
        self.action_handlers["DIG"] = self.handle_dig
        self.action_handlers["SPAWN"] = self.handle_spawn
        self.action_handlers["FILL"] = self.handle_fill
        self.action_handlers["DANCE"] = self.handle_dance
        self.action_handlers["MODIFY"] = self.handle_modify
        ### FIXME generalize these
        self.action_handlers["GET"] = self.handle_get
        self.action_handlers["DROP"] = self.handle_drop

        self.task_objects = {
            "move": tasks.Move,
            "undo": tasks.Undo,
            "build": tasks.Build,
            "destroy": tasks.Destroy,
            "spawn": tasks.Spawn,
            "fill": tasks.Fill,
            "dig": tasks.Dig,
            "dance": tasks.Dance,
            "point": tasks.Point,
            "dancemove": tasks.DanceMove,
            "get": tasks.Get,
            "drop": tasks.Drop,
            "control": ControlBlock,
        }

    def handle_modify(self, agent, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and handles a 'modify' command by either replying back or pushing
        appropriate tasks to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """
        default_ref_d = {"filters": {"location": SPEAKERLOOK}}
        ref_d = d.get("reference_object", default_ref_d)
        # only modify blockobjects...
        objs = self.subinterpret["reference_objects"](
            self, speaker, ref_d, extra_tags=["_physical_object", "VOXEL_OBJECT"]
        )
        if len(objs) == 0:
            raise ErrorWithResponse("I don't understand what you want me to modify.")

        m_d = d.get("modify_dict")
        if not m_d:
            raise ErrorWithResponse(
                "I think you want me to modify an object but am not sure what to do"
            )
        tasks = []
        for obj in objs:
            if m_d["modify_type"] == "THINNER" or m_d["modify_type"] == "THICKER":
                destroy_task_data, build_task_data = handle_thicken(self, speaker, m_d, obj)
            elif m_d["modify_type"] == "REPLACE":
                destroy_task_data, build_task_data = handle_replace(
                    self, speaker, m_d, obj, block_data=self.block_data
                )
            elif m_d["modify_type"] == "SCALE":
                destroy_task_data, build_task_data = handle_scale(self, speaker, m_d, obj)
            elif m_d["modify_type"] == "RIGIDMOTION":
                destroy_task_data, build_task_data = handle_rigidmotion(self, speaker, m_d, obj)
            elif m_d["modify_type"] == "FILL" or m_d["modify_type"] == "HOLLOW":
                destroy_task_data, build_task_data = handle_fill(
                    self, speaker, m_d, obj, block_data=self.block_data
                )
            else:
                raise ErrorWithResponse(
                    "I think you want me to modify an object but am not sure what to do (parse error)"
                )

            if build_task_data:
                tasks.append(self.task_objects["build"](agent, build_task_data))

            if destroy_task_data:
                tasks.append(self.task_objects["build"](agent, destroy_task_data))

        return maybe_task_list_to_control_block(tasks, agent), None, None

    def handle_spawn(self, agent, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and handles a 'spawn' command by either replying back or
        pushing a Spawn task to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """
        # FIXME! use filters appropriately, don't search by hand
        filters_d = d.get("reference_object", {}).get("filters", {})
        spawn_triples = filters_d.get("triples", [])
        if not spawn_triples:
            raise ErrorWithResponse("I don't understand what you want me to spawn.")
        names = [t.get("obj_text") for t in spawn_triples if t.get("pred_text", "") == "has_name"]
        if not any(names):
            raise ErrorWithResponse("I don't understand what you want me to spawn.")
        # if multiple possible has_name triples, just pick the first:
        object_name = names[0]
        #############################################################
        # FIXME! use FILTERS handle this properly...!
        # repeats are hacky (and wrong) too because not using FILTERS
        #############################################################
        schematic = self.memory.get_mob_schematic_by_name(object_name)
        if not schematic:
            raise ErrorWithResponse("I don't know how to spawn: %r." % (object_name))

        object_idm = list(schematic.blocks.values())[0]
        location_d = d.get("location", SPEAKERLOOK)
        mems = self.subinterpret["reference_locations"](self, speaker, location_d)
        steps, reldir = interpret_relative_direction(self, location_d)
        pos, _ = self.subinterpret["specify_locations"](self, speaker, mems, steps, reldir)
        # FIXME, not using selector properly (but need to use FILTERS first)
        repeat = filters_d.get("selector", {}).get("return_quantity", {}).get("random", "1")
        repeat_times = int(number_from_span(repeat))
        tasks = []
        for i in range(repeat_times):
            task_data = {"object_idm": object_idm, "pos": pos, "action_dict": d}
            tasks.append(self.task_objects["spawn"](agent, task_data))
        return maybe_task_list_to_control_block(tasks, agent), None, None

    def handle_build(self, agent, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and perception and handles a 'build' command by either pushing a dialogue object
        or pushing a Build task to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """
        # Get the segment to build
        if "reference_object" in d:
            # handle copy
            ##########FIXME remove this when DSL updated!!!
            md = deepcopy(d)
            convert_location_to_selector(md["reference_object"])
            objs = self.subinterpret["reference_objects"](
                self,
                speaker,
                md["reference_object"],
                extra_tags=["VOXEL_OBJECT"],
                loose_speakerlook=True,
            )
            if len(objs) == 0:
                raise ErrorWithResponse("I don't understand what you want me to build")
            tagss = [
                [(p, v) for (_, p, v) in self.memory.get_triples(subj=obj.memid)] for obj in objs
            ]
            interprets = [
                [list(obj.blocks.items()), obj.memid, tags] for (obj, tags) in zip(objs, tagss)
            ]
        else:  # a schematic
            interprets = interpret_schematic(self,
                                             speaker,
                                             d.get("schematic", {}),
                                             self.block_data,
                                             self.special_shape_functions)

        # Get the locations to build
        location_d = d.get("location", SPEAKERLOOK)
        mems = self.subinterpret["reference_locations"](self, speaker, location_d)
        steps, reldir = interpret_relative_direction(self, location_d)
        origin, offsets = self.subinterpret["specify_locations"](
            self,
            speaker,
            mems,
            steps,
            reldir,
            repeat_dir=get_repeat_dir(location_d),
            objects=interprets,
        )
        interprets_with_offsets = [
            (blocks, mem, tags, off) for (blocks, mem, tags), off in zip(interprets, offsets)
        ]

        tasks_data = []
        for schematic, schematic_memid, tags, offset in interprets_with_offsets:
            og = np.array(origin) + offset
            task_data = {
                "blocks_list": schematic,
                "origin": og,
                "schematic_memid": schematic_memid,
                "schematic_tags": tags,
                "action_dict": d,
            }

            tasks_data.append(task_data)

        tasks = []
        for td in tasks_data:
            t = self.task_objects["build"](agent, td)
            tasks.append(t)
        logging.info("Adding {} Build tasks to stack".format(len(tasks)))
        return maybe_task_list_to_control_block(tasks, agent), None, None

    def handle_fill(self, agent, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and perception and handles a 'fill' command by either pushing a dialogue object
        or pushing a Fill task to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """
        tasks = []
        r = d.get("reference_object")
        if not r.get("filters"):
            r["filters"] = {"location", SPEAKERLOOK}

        # Get the reference location
        location_d = r["filters"].get("location", SPEAKERLOOK)
        mems = self.subinterpret["reference_locations"](self, speaker, location_d)
        steps, reldir = interpret_relative_direction(self, location_d)
        location, _ = self.subinterpret["specify_locations"](self, speaker, mems, steps, reldir)

        # Get nearby holes
        holes = heuristic_perception.get_all_nearby_holes(agent, location, self.block_data)
        # Choose the best ones to fill
        holes = filter_by_sublocation(self, speaker, holes, r, loose=True)

        if holes is None:
            # FIXME: in stage III, replace agent with the lowlevel interface to sending chats
            raise ErrorWithResponse("I don't understand what holes you want me to fill.")
        tasks = []
        for hole in holes:
            poss = list(hole.blocks.keys())
            try:
                fill_memid = agent.memory.get_triples(subj=hole.memid, pred_text="has_fill_type")[
                    0
                ][2]
                fill_block_mem = self.memory.get_mem_by_id(fill_memid)
                fill_idm = (fill_block_mem.b, fill_block_mem.m)
            except:
                # FIXME use a constant name
                fill_idm = (3, 0)
            schematic, tags = interpret_fill_schematic(
                self, speaker, d.get("schematic", {}), poss, fill_idm, self.block_data
            )
            origin = np.min([xyz for (xyz, bid) in schematic], axis=0)
            task_data = {
                "blocks_list": schematic,
                "force": True,
                "origin": origin,
                "verbose": False,
                "embed": True,
                "fill_message": True,
                "schematic_tags": tags,
            }

            tasks.append(self.task_objects["build"](agent, task_data))

        if len(holes) > 1:
            self.memory.dialogue_stack_append_new(Say, "Ok. I'll fill up the holes.")
        else:
            self.memory.dialogue_stack_append_new(Say, "Ok. I'll fill that hole up.")

        return maybe_task_list_to_control_block(tasks, agent), None, None

    def handle_destroy(self, agent, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and perception and handles a 'destroy' command by either pushing a dialogue object
        or pushing a Destroy task to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """
        default_ref_d = {"filters": {"location": SPEAKERLOOK}}
        ref_d = d.get("reference_object", default_ref_d)
        objs = self.subinterpret["reference_objects"](
            self, speaker, ref_d, extra_tags=["_destructible"]
        )
        if len(objs) == 0:
            raise ErrorWithResponse("I don't understand what you want me to destroy.")

        # don't kill mobs
        if all(isinstance(obj, MobNode) for obj in objs):
            raise ErrorWithResponse("I don't kill animals, sorry!")
        if all(isinstance(obj, PlayerNode) for obj in objs):
            raise ErrorWithResponse("I don't kill players, sorry!")
        objs = [obj for obj in objs if not isinstance(obj, MobNode)]
        tasks = []
        for obj in objs:
            if hasattr(obj, "blocks"):
                schematic = list(obj.blocks.items())
                task_data = {"schematic": schematic, "action_dict": d}
                tasks.append(self.task_objects["destroy"](agent, task_data))
        logging.info("Added {} Destroy tasks to stack".format(len(tasks)))
        return maybe_task_list_to_control_block(tasks, agent), None, None

    def handle_dig(self, agent, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and perception and handles a 'dig' command by either pushing a dialogue object
        or pushing a Dig task to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """

        def new_tasks():
            attrs = {}
            schematic_triples = d.get("schematic", {}).get("filters", {}).get("triples",
                                                                              [{'pred_text': 'has_size',
                                                                                'obj_text': '2'}])
            # schematic_d = d.get("schematic", {"has_size": 2})
            # set the attributes of the hole to be dug.
            schematic_d = {}
            for triple in schematic_triples:
                schematic_d[triple['pred_text']] = triple['obj_text']
                
            for dim, default in [("depth", 1), ("length", 1), ("width", 1)]:
                key = "has_{}".format(dim)
                if key in schematic_d:
                    attrs[dim] = word_to_num(schematic_d[key])
                elif "has_size" in schematic_d:
                    attrs[dim] = interpret_size(self, schematic_d["has_size"])
                else:
                    attrs[dim] = default
            padding = (attrs["depth"] + 4, attrs["length"] + 4, attrs["width"] + 4)
            location_d = d.get("location", SPEAKERLOOK)
            repeat_num = get_repeat_num(d)
            repeat_dir = get_repeat_dir(d)
            mems = self.subinterpret["reference_locations"](self, speaker, location_d)
            steps, reldir = interpret_relative_direction(self, location_d)
            origin, offsets = self.subinterpret["specify_locations"](
                self,
                speaker,
                mems,
                steps,
                reldir,
                repeat_num=repeat_num,
                repeat_dir=repeat_dir,
                padding=padding,
            )
            # add dig tasks in a loop
            tasks_todo = []
            for offset in offsets:
                og = np.array(origin) + offset
                t = self.task_objects["dig"](agent, {"origin": og, "action_dict": d, **attrs})
                tasks_todo.append(t)
            return maybe_task_list_to_control_block(tasks_todo, agent)

        if "remove_condition" in d:
            condition = self.subinterpret["condition"](self, speaker, d["remove_condition"])
            return (
                [
                    self.task_objects["control"](
                        agent,
                        data={
                            "new_tasks": new_tasks,
                            "remove_condition": condition,
                            "action_dict": d,
                        },
                    )
                ],
                None,
                None,
            )
        else:
            return new_tasks(), None, None

    def handle_dance(self, agent, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and perception and handles a 'dance' command by either pushing a dialogue object
        or pushing a Dance task to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """

        def new_tasks():
            repeat = get_repeat_num(d)
            tasks_to_do = []
            # only go around the x has "around"; FIXME allow other kinds of dances
            location_d = d.get("location")
            if location_d is not None:
                rd = location_d.get("relative_direction")
                if rd is not None and (
                        rd == "AROUND" or rd == "CLOCKWISE" or rd == "ANTICLOCKWISE"
                ):
                    ref_obj = None
                    location_reference_object = location_d.get("reference_object")
                    if location_reference_object:
                        objmems = self.subinterpret["reference_objects"](
                            self, speaker, location_reference_object
                        )
                        if len(objmems) == 0:
                            raise ErrorWithResponse("I don't understand where you want me to go.")
                        ref_obj = objmems[0]
                    for i in range(repeat):
                        refmove = dance.RefObjMovement(
                            agent,
                            ref_object=ref_obj,
                            relative_direction=location_d["relative_direction"],
                        )
                        t = self.task_objects["dance"](agent, {"movement": refmove})
                        tasks_to_do.append(t)
                    return maybe_task_list_to_control_block(tasks_to_do, agent)

            dance_type = d.get("dance_type", {})
            if dance_type.get("point"):
                target = self.subinterpret["point_target"](self, speaker, dance_type["point"])
                for i in range(repeat):
                    t = self.task_objects["point"](agent, {"target": target})
                    tasks_to_do.append(t)
            # MC bot does not control body turn separate from head
            elif dance_type.get("look_turn") or dance_type.get("body_turn"):
                lt = dance_type.get("look_turn") or dance_type.get("body_turn")
                f = self.subinterpret["facing"](self, speaker, lt)
                for i in range(repeat):
                    t = self.task_objects["dancemove"](agent, f)
                    tasks_to_do.append(t)
            else:
                if location_d is None:
                    dance_location = None
                else:
                    mems = self.subinterpret["reference_locations"](self, speaker, location_d)
                    steps, reldir = interpret_relative_direction(self, location_d)
                    dance_location, _ = self.subinterpret["specify_locations"](
                        self, speaker, mems, steps, reldir
                    )
                filters_d = dance_type.get("filters", {})
                filters_d["memory_type"] = "DANCES"
                F = self.subinterpret["filters"](self, speaker, dance_type.get("filters", {}))
                dance_memids, _ = F()
                # TODO correct selector in filters
                if dance_memids:
                    dance_memid = random.choice(dance_memids)
                    dance_mem = self.memory.get_mem_by_id(dance_memid)
                    for i in range(repeat):
                        dance_obj = dance.Movement(
                            agent=agent, move_fn=dance_mem.dance_fn, dance_location=dance_location
                        )
                        t = self.task_objects["dance"](agent, {"movement": dance_obj})
                        tasks_to_do.append(t)
                else:
                    # dance out of scope
                    raise ErrorWithResponse("I don't know how to do that movement yet.")
            return maybe_task_list_to_control_block(tasks_to_do, agent)

        if "remove_condition" in d:
            condition = self.subinterpret["condition"](self, speaker, d["remove_condition"])
            return (
                [
                    self.task_objects["control"](
                        agent,
                        data={
                            "new_tasks_fn": new_tasks,
                            "remove_condition": condition,
                            "action_dict": d,
                        },
                    )
                ],
                None,
                None,
            )
        else:
            return new_tasks(), None, None

    # FIXME this is not compositional/does not handle loops ("get all the x")
    def handle_get(self, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and perception and handles a 'get' command by either pushing a dialogue object
        or pushing a Get task to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """
        ref_d = d.get("reference_object", None)
        if not ref_d:
            raise ErrorWithResponse("I don't understand what you want me to get.")

        objs = self.subinterpret["reference_objects"](
            self, speaker, ref_d, extra_tags=["_on_ground"]
        )
        if len(objs) == 0:
            raise ErrorWithResponse("I don't understand what you want me to get.")
        obj = [obj for obj in objs if isinstance(obj, ItemStackNode)][0]
        item_stack = agent.get_item_stack(obj.eid)
        idm = (item_stack.item.id, item_stack.item.meta)
        task_data = {"idm": idm, "pos": obj.pos, "eid": obj.eid, "memid": obj.memid}
        return self.task_objects["get"](agent, task_data), None, None

    # FIXME this is not compositional/does not handle loops ("get all the x")
    def handle_drop(self, agent, speaker, d) -> Tuple[Any, Optional[str], Any]:
        """This function reads the dictionary, resolves the missing details using memory
        and perception and handles a 'drop' command by either pushing a dialogue object
        or pushing a Drop task to the task stack.

        Args:
            speaker: speaker_id or name.
            d: the complete action dictionary
        """
        ref_d = d.get("reference_object", None)
        if not ref_d:
            raise ErrorWithResponse("I don't understand what you want me to drop.")

        objs = self.subinterpret["reference_objects"](
            self, speaker, ref_d, extra_tags=["_in_inventory"]
        )
        if len(objs) == 0:
            raise ErrorWithResponse("I don't understand what you want me to drop.")

        obj = [obj for obj in objs if isinstance(obj, ItemStackNode)][0]
        item_stack = agent.get_item_stack(obj.eid)
        idm = (item_stack.item.id, item_stack.item.meta)
        task_data = {"eid": obj.eid, "idm": idm, "memid": obj.memid}
        return self.task_objects["drop"](agent, task_data), None, None
