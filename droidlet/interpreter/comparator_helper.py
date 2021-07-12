"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from droidlet.shared_data_structs import ErrorWithResponse
from .attribute_helper import AttributeInterpreter, maybe_specific_mem, interpret_span_value
from droidlet.interpreter.condition_classes import Comparator
from droidlet.memory.memory_values import MemoryColumnValue
from droidlet.memory.memory_attributes import ComparatorAttribute

# TODO distance between
# TODO make this more modular.  what if we want to redefine just distance_between in a new agent?
def interpret_comparator(interpreter, speaker, d, is_condition=True):
    """subinterpreter to interpret comparators
    args:
    interpreter:  root interpreter.
    speaker (str): The name of the player/human/agent who uttered
        the chat resulting in this interpreter
    d: logical form from semantic parser
    """
    # TODO add some input checks
    get_attribute = interpreter.subinterpret.get("attributes", AttributeInterpreter())
    value_extractors = {}
    for inp_pos in ["input_left", "input_right"]:
        inp = d[inp_pos]["value_extractor"]
        if type(inp) is str:
            if inp == "NULL":
                value_extractors[inp_pos] = None
            else:
                # this is a span
                cm = d.get("comparison_measure")
                v = interpret_span_value(interpreter, speaker, inp, comparison_measure=cm)
                value_extractors[inp_pos] = v
        elif inp.get("filters"):
            # this is a filter
            # TODO FIXME! deal with count
            # TODO logical form etc.?
            # FIXME handle errors/None return in AttributeInterpeter
            inp_filt = inp["filters"]
            if inp_filt["output"].get("attribute"):
                attribute = get_attribute(interpreter, speaker, inp_filt["output"]["attribute"])
            else:
                raise Exception(
                    "filters comparator with no attribute specified {}".format(inp_filt)
                )
            mem, query = maybe_specific_mem(interpreter, speaker, inp)
            # TODO wrap this in a ScaledValue using condtition.convert_comparison_value
            # and "comparison_measure"
            value_extractors[inp_pos] = MemoryColumnValue(
                interpreter.memory, attribute, query=query, mem=mem
            )
        else:
            raise ErrorWithResponse(
                "I don't know understand that condition, looks like a comparator but value is not filters or span"
            )
    comparison_type = d.get("comparison_type")
    if not comparison_type:
        ErrorWithResponse(
            "I think you want me to compare two things in a condition, but am not sure what type of comparison"
        )
    if is_condition:
        return Comparator(
            interpreter.memory,
            value_left=value_extractors["input_left"],
            value_right=value_extractors["input_right"],
            comparison_type=comparison_type,
        )
    else:
        return ComparatorAttribute(
            interpreter.memory,
            value_left=value_extractors["input_left"],
            value_right=value_extractors["input_right"],
            comparison_type=comparison_type,
        )
