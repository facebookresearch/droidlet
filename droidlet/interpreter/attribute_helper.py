"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from copy import deepcopy
from droidlet.memory.memory_attributes import (
    LinearExtentAttribute,
    TableColumn,
    ListAttribute,
    TripleWalk,
    AttributeSequence,
    BBoxSize,
)
from droidlet.memory.memory_values import LinearExtentValue, FixedValue, convert_comparison_value
from droidlet.base_util import number_from_span
from ..shared_data_structs import ErrorWithResponse
from droidlet.memory.memory_nodes import ReferenceObjectNode
from .interpreter_utils import tags_from_dict

"""
Each of these take args:
interpreter:  root interpreter.
speaker (str): The name of the player/human/agent who uttered 
    the chat resulting in this interpreter
d: logical form from semantic parser
"""


def interpret_span_value(interpreter, speaker, d, comparison_measure=None):
    """
    Make a FixedValue object from a number span

    the optional arg comparison_measure should be something that can be handled by
    the convert_comparison_value function
    """
    num = number_from_span(d)
    if num:
        v = FixedValue(interpreter.memory, num)
        # always convert everything to internal units
        # FIXME handle this better
        v = convert_comparison_value(v, comparison_measure)
    else:
        v = FixedValue(interpreter.memory, d)
    return v


def maybe_specific_mem(interpreter, speaker, ref_obj_d):
    """
    check if the reference object logical form corresponds to a ReferenceObject already
    in memory.  used e.g. in Values and Conditions, to distinguish between a ReferenceObject not in
    memory now but to be searched for when checking the condition
    """
    mem = None
    query = ""
    cands = None
    # FIXME! make a "get_special_reference" fn
    if ref_obj_d.get("special_reference"):
        # this is a special ref object, not filters....
        cands = interpreter.subinterpret["reference_objects"](interpreter, speaker, ref_obj_d)
        return cands[0], None
    filters_d = ref_obj_d.get("filters", {})
    coref = filters_d.get("contains_coreference", "NULL")
    if coref != "NULL":
        # this is a particular entity etc, don't search for the mem at check() time
        if isinstance(coref, ReferenceObjectNode):
            mem = coref
        else:
            sub_ref_obj_d = deepcopy(ref_obj_d)
            # del this to stop recursion, otherwise will end up here again
            del sub_ref_obj_d["filters"]["contains_coreference"]
            cands = interpreter.subinterpret["reference_objects"](
                interpreter, speaker, sub_ref_obj_d
            )
            if not cands:
                # FIXME fix this error
                raise ErrorWithResponse(
                    "I don't know which objects' attribute you are talking about"
                )
            # FIXME! if more than one? ask? use the filters?
            else:
                mem = cands[0]
    else:
        # this object is only defined by the filters and might be different at different moments
        # FIXME use FILTERS!!
        # should interpret as normal filter at this point...
        tags = tags_from_dict(filters_d)
        if tags:
            where = " AND ".join(["(has_tag={})".format(tag) for tag in tags])
            query = "SELECT MEMORY FROM ReferenceObject WHERE (" + where + ")"

    return mem, query


def interpret_linear_extent(interpreter, speaker, d, force_value=False):
    """
    returns a LinearExtentAttribute or LinearExtentValue.

    the force_value arg forces the output to be a LinearExtentValue
    """
    location_data = {}
    if d.get("normalized"):
        location_data["normalized"] = True
    default_frame = getattr(interpreter, "default_frame", "AGENT")
    frame = d.get("frame", default_frame)
    if frame == "SPEAKER":
        frame = speaker
    if type(frame) is dict:
        frame = frame.get("player_span", "unknown_player")
    if frame == "AGENT":
        location_data["frame"] = "AGENT"
    else:
        p = interpreter.memory.get_player_by_name(frame)
        if p:
            location_data["frame"] = p.eid
        else:
            raise ErrorWithResponse("I don't understand in whose frame of reference you mean")
    location_data["relative_direction"] = d.get("relative_direction", "AWAY")
    # FIXME!!!! has_measure

    rd = d.get("source")
    fixed_role = "source"
    if not rd:
        rd = d.get("destination")
        fixed_role = "destination"
    rd = rd["reference_object"]

    mem, _ = maybe_specific_mem(interpreter, speaker, rd)
    # FIXME this does not allow searching at run time, only at build time!
    if not mem:
        mems = interpreter.subinterpret["reference_objects"](interpreter, speaker, rd)
        if not mems:
            raise ErrorWithResponse("I don't know what you're referring to")
        mem = mems[0]
    #        # should we do this?
    #        if not f.get("selector"):
    #            f["selector"] = (
    #                ref_obj_lf_to_selector(SPEAKERLOOK)
    #                if default_frame == "SPEAKER"
    #                else ref_obj_lf_to_selector(AGENTPOS)
    #            )
    #        F = interpreter.subinterpret["filters"](interpreter, speaker, f)
    #        location_data["filter"] = F
    L = LinearExtentAttribute(interpreter.memory, location_data, mem=mem, fixed_role=fixed_role)

    # TODO some sort of sanity check here, these should be rare:
    if (d.get("source") and d.get("destination")) or force_value:
        rd = d.get("destination")
        mem = None
        sd = None
        if rd:
            mem, query = maybe_specific_mem(interpreter, speaker, rd["filters"])
        L = LinearExtentValue(interpreter.memory, L, mem=mem, query=query)

    return L


def interpret_task_info(interpreter, speaker, d):
    # name already handled, currently only other possibility is
    # "task_info": {"reference_object": ATTRIBUTE}
    task_info = d.get("task_info")
    if not task_info:
        raise ValueError("task info malformed: {}".format(task_info))
    ref_obj_attr_d = task_info.get("reference_object")
    if not ref_obj_attr_d:
        raise ValueError("task info malformed: {}".format(task_info))
    if not ref_obj_attr_d.get("attribute"):
        raise ValueError("task info malformed: {}".format(task_info))

    # we probably should rearrange FILTERS spec so that the task ref obj is the returned memory, not the task...
    get_refobj = TripleWalk(interpreter.memory, [("task_reference_object", "obj_variable")])
    refobj_attr = interpreter.subinterpret["attribute"](
        interpreter, speaker, ref_obj_attr_d["attribute"]
    )
    return AttributeSequence(interpreter.memory, [get_refobj, refobj_attr])


class AttributeInterpreter:
    def __call__(self, interpreter, speaker, d_attribute, get_all=False):
        if type(d_attribute) is str:
            if (
                d_attribute.lower() == "height"
                or d_attribute.lower() == "width"
                or d_attribute.lower() == "height"
                or d_attribute.lower() == "size"
            ):
                return BBoxSize(interpreter.memory, d_attribute.lower())
            d_attribute = CANONICALIZE_ATTRIBUTES.get(d_attribute.lower())
            if d_attribute and type(d_attribute) is str:
                # FIXME!!! merge/backoff to things like get_property_value
                return TableColumn(interpreter.memory, d_attribute, get_all=get_all)
            elif d_attribute and type(d_attribute) is list:
                alist = [self.__call__(interpreter, speaker, a) for a in d_attribute]
                return ListAttribute(interpreter.memory, alist)
        elif d_attribute.get("task_info"):
            return interpret_task_info(interpreter, speaker, d_attribute)
        elif d_attribute.get("linear_extent"):
            return interpret_linear_extent(interpreter, speaker, d_attribute["linear_extent"])


CANONICALIZE_ATTRIBUTES = {
    "x": "x",
    "y": "y",
    "z": "z",
    "location": ["x", "y", "z"],
    "ref_type": "ref_type",
    "head_pitch": "pitch",
    "head_yaw": "yaw",  # FIXME!!! prob should have pose type in memory
    "body_yaw": "yaw",  # FIXME!!! prob should have pose type in memory
    "name": "has_name",
    "colour": "has_colour",
    "tag": "has_tag",
    "born_time": "create_time",
    "modify_time": "updated_time",
    "visit_time": "attended_time",  # FIXME!!
    "run_count": "run_count"
    # "speaker","finished_time", "chat", "logical_form" ... tasks not supported yet
}
