"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from droidlet.interpreter import SPEAKERLOOK, AGENTPOS
from copy import deepcopy


def command(d):
    if type(d) is list:
        return {"dialogue_type": "HUMAN_GIVE_COMMAND", "action_sequence": d}
    else:
        return {"dialogue_type": "HUMAN_GIVE_COMMAND", "action_sequence": [d]}


ATTRIBUTES = {
    "x": {"attribute": "x"},
    "distance from me": {
        "attribute": {
            "linear_extent": {
                "relative_direction": "AWAY",
                "source": {"reference_object": {"special_reference": "SPEAKER"}},
            }
        }
    },
    "create time": {"attribute": "BORN_TIME"},
    "number of blocks": {"num_blocks": {"block_filters": {}}},
    "number of blue blocks": {"num_blocks": {"block_filters": {"has_colour": "blue"}}},
}


FILTERS = {
    "that cow": {
        "triples": [{"pred_text": "has_name", "obj_text": "cow"}],
        "contains_coreference": "resolved",
        "selector": {"location": SPEAKERLOOK},
    },
    "that cube": {
        "triples": [{"pred_text": "has_name", "obj_text": "cube"}],
        "contains_coreference": "resolved",
        "selector": {"location": SPEAKERLOOK},
    },
    "a cow": {"triples": [{"pred_text": "has_name", "obj_text": "cow"}]},
    "a random cube": {
        "selector": {"return_quantity": {"random": "1"}},
        "triples": [{"pred_text": "has_name", "obj_text": "cube"}],
    },
    "two random cubes": {
        "selector": {"return_quantity": {"random": "2"}},
        "triples": [{"pred_text": "has_name", "obj_text": "cube"}],
    },
    "a cube": {"triples": [{"pred_text": "has_name", "obj_text": "cube"}]},
    "where I am looking": {"selector": {"location": SPEAKERLOOK}},
    "my location": {"selector": {"location": AGENTPOS}},
    "number of blocks in blue cube": {
        "output": {"attribute": ATTRIBUTES["number of blocks"]},
        "triples": [
            {"pred_text": "has_name", "obj_text": "cube"},
            {"pred_text": "has_colour", "obj_text": "blue"},
        ],
    },
}

REFERENCE_OBJECTS = {
    "where I am looking": {
        "filters": FILTERS["where I am looking"],
        "text_span": "where I'm looking",
    },
    "that cow": {"filters": FILTERS["that cow"]},
    "a cow": {"filters": FILTERS["a cow"]},
    "that cube": {"filters": FILTERS["that cube"]},
    "a cube": {"filters": FILTERS["a cube"]},
    "me": {"special_reference": "AGENT"},
}

ATTRIBUTES["distance from that cube"] = {
    "attribute": {
        "linear_extent": {
            "relative_direction": "AWAY",
            "source": {"reference_object": REFERENCE_OBJECTS["that cube"]},
        }
    }
}

# FIXME "built" should check for player made or agent made
FILTERS["the first thing that was built"] = {
    "selector": {
        "return_quantity": {
            "argval": {
                "polarity": "MIN",
                "ordinal": "FIRST",
                "quantity": ATTRIBUTES["create time"],
            }
        }
    },
    "triples": [{"pred_text": "has_tag", "obj_text": "VOXEL_OBJECT"}],
}
FILTERS["the last thing that was built"] = {
    "selector": {
        "return_quantity": {
            "argval": {
                "polarity": "MAX",
                "ordinal": "FIRST",
                "quantity": ATTRIBUTES["create time"],
            }
        }
    },
    "triples": [{"pred_text": "has_tag", "obj_text": "VOXEL_OBJECT"}],
}
FILTERS["number of blocks in the first thing built"] = {
    "output": {"attribute": ATTRIBUTES["number of blocks"]},
    "selector": {
        "return_quantity": {
            "argval": {
                "polarity": "MIN",
                "ordinal": "FIRST",
                "quantity": ATTRIBUTES["create time"],
            }
        }
    },
    "triples": [{"pred_text": "has_tag", "obj_text": "VOXEL_OBJECT"}],
}
FILTERS["number of blocks in the second thing built"] = {
    "output": {"attribute": ATTRIBUTES["number of blocks"]},
    "selector": {
        "return_quantity": {
            "argval": {
                "polarity": "MIN",
                "ordinal": "SECOND",
                "quantity": ATTRIBUTES["create time"],
            }
        }
    },
    "triples": [{"pred_text": "has_tag", "obj_text": "VOXEL_OBJECT"}],
}
FILTERS["number of blocks in the last thing built"] = {
    "output": {"attribute": ATTRIBUTES["number of blocks"]},
    "selector": {
        "return_quantity": {
            "argval": {
                "polarity": "MAX",
                "ordinal": "FIRST",
                "quantity": ATTRIBUTES["create time"],
            }
        }
    },
    "triples": [{"pred_text": "has_tag", "obj_text": "VOXEL_OBJECT"}],
}


INTERPRETER_POSSIBLE_ACTIONS = {
    "destroy_speaker_look": {
        "action_type": "DESTROY",
        "reference_object": {
            "filters": {"selector": {"location": SPEAKERLOOK}},
            "text_span": "where I'm looking",
        },
    },
    "spawn_5_sheep": {
        "action_type": "SPAWN",
        "reference_object": {
            "filters": {
                "triples": [{"pred_text": "has_name", "obj_text": "sheep"}],
                "selector": {"return_quantity": {"random": "5"}, "same": "ALLOWED"},
            },
            "text_span": "sheep",
        },
    },
    "copy_speaker_look_to_agent_pos": {
        "action_type": "BUILD",
        "reference_object": {
            "filters": {"selector": {"location": SPEAKERLOOK}},
            "text_span": "where I'm looking",
        },
        "location": {
            "reference_object": {"special_reference": "AGENT"},
            "text_span": "where I am",
        },
    },
    "build_small_sphere": {
        "action_type": "BUILD",
        "schematic": {
            "filters": {
                "triples": [
                    {"pred_text": "has_name", "obj_text": "sphere"},
                    {"pred_text": "has_size", "obj_text": "small"},
                ]
            },
            "text_span": "small sphere",
        },
    },
    "build_1x1x1_cube": {
        "action_type": "BUILD",
        "schematic": {
            "filters": {
                "triples": [
                    {"pred_text": "has_name", "obj_text": "cube"},
                    {"pred_text": "has_size", "obj_text": "1 x 1 x 1"},
                ]
            },
            "text_span": "1 x 1 x 1 cube",
        },
    },
    "move_speaker_pos": {
        "action_type": "MOVE",
        "location": {"reference_object": {"special_reference": "SPEAKER"}, "text_span": "to me"},
    },
    "build_diamond": {
        "action_type": "BUILD",
        "schematic": {
            "filters": {"triples": [{"pred_text": "has_name", "obj_text": "diamond"}]},
            "text_span": "diamond",
        },
    },
    "build_gold_cube": {
        "action_type": "BUILD",
        "schematic": {
            "filters": {
                "triples": [
                    {"pred_text": "has_block_type", "obj_text": "gold"},
                    {"pred_text": "has_name", "obj_text": "cube"},
                ]
            },
            "text_span": "gold cube",
        },
    },
    "build_red_cube": {
        "action_type": "BUILD",
        "location": {"reference_object": {"special_reference": "SPEAKER_LOOK"}},
        "schematic": {
            "filters": {
                "triples": [
                    {"pred_text": "has_colour", "obj_text": "red"},
                    {"pred_text": "has_name", "obj_text": "cube"},
                ]
            },
            "text_span": "red cube",
        },
    },
    "destroy_red_cube": {
        "action_type": "DESTROY",
        "reference_object": {
            "filters": {
                "triples": [
                    {"pred_text": "has_name", "obj_text": "cube"},
                    {"pred_text": "has_colour", "obj_text": "red"},
                ]
            },
            "text_span": "red cube",
        },
    },
    "fill_all_holes_speaker_look": {
        "action_type": "FILL",
        "reference_object": {
            "filters": {"selector": {"location": SPEAKERLOOK, "return_quantity": "ALL"}},
            "text_span": "where I'm looking",
        },
    },
    "go_to_tree": {
        "action_type": "MOVE",
        "location": {
            "reference_object": {
                "filters": {"triples": [{"pred_text": "has_name", "obj_text": "tree"}]}
            },
            "text_span": "tree",
        },
    },
    "build_square_height_1": {
        "action_type": "BUILD",
        "schematic": {
            "filters": {
                "triples": [
                    {"pred_text": "has_name", "obj_text": "square"},
                    {"pred_text": "has_height", "obj_text": "1"},
                ]
            },
            "text_span": "square height 1",
        },
    },
    "stop": {"action_type": "STOP"},
    "fill_speaker_look": {
        "action_type": "FILL",
        "reference_object": {
            "filters": {"selector": {"location": SPEAKERLOOK}},
            "text_span": "where I'm looking",
        },
    },
    "fill_speaker_look_gold": {
        "action_type": "FILL",
        "schematic": {
            "filters": {"triples": [{"pred_text": "has_block_type", "obj_text": "gold"}]}
        },
        "reference_object": {
            "filters": {"selector": {"location": SPEAKERLOOK}},
            "text_span": "where I'm looking",
        },
    },
}

BUILD_COMMANDS = {
    "build a gold cube at 0 66 0": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "BUILD",
                "schematic": {
                    "filters": {
                        "triples": [
                            {"pred_text": "has_name", "obj_text": "cube"},
                            {"pred_text": "has_block_type", "obj_text": "gold"},
                        ]
                    }
                },
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "0 66 0"}}
                },
            }
        ],
    },
    "build a small cube": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "BUILD",
                "schematic": {
                    "filters": {
                        "triples": [
                            {"pred_text": "has_name", "obj_text": "cube"},
                            {"pred_text": "has_size", "obj_text": "small"},
                        ]
                    }
                },
            }
        ],
    },
    "build a circle to the left of the circle": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "BUILD",
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "circle"}]}
                    },
                    "relative_direction": "LEFT",
                    "text_span": "to the left of the circle",
                },
                "schematic": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "circle"}]},
                    "text_span": "circle",
                },
            }
        ],
    },
    "copy where I am looking to here": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["copy_speaker_look_to_agent_pos"]],
    },
    "build a small sphere": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["build_small_sphere"]],
    },
    "build a 1x1x1 cube": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["build_1x1x1_cube"]],
    },
    "build a diamond": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["build_diamond"]],
    },
    "build a gold cube": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["build_gold_cube"]],
    },
    "build a 9 x 9 stone rectangle": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "BUILD",
                "schematic": {
                    "filters": {
                        "triples": [
                            {"pred_text": "has_block_type", "obj_text": "stone"},
                            {"pred_text": "has_name", "obj_text": "rectangle"},
                            {"pred_text": "has_height", "obj_text": "9"},
                            {"pred_text": "has_base", "obj_text": "9"},
                        ]
                    },  # has_base doesn't belong in "rectangle"
                    "text_span": "9 x 9 stone rectangle",
                },
            }
        ],
    },
    "build a square with height 1": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["build_square_height_1"]],
    },
    "build a red cube": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["build_red_cube"]],
    },
    "build a fluffy here": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "BUILD",
                "schematic": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "fluffy"}]}
                },
                "location": {"reference_object": {"special_reference": "AGENT"}},
            }
        ],
    },
}

SPAWN_COMMANDS = {
    "spawn 5 sheep": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["spawn_5_sheep"]],
    }
}

DESTROY_COMMANDS = {
    "destroy it": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "DESTROY",
                "reference_object": {"filters": {"contains_coreference": "yes"}},
            }
        ],
    },
    "destroy where I am looking": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["destroy_speaker_look"]],
    },
    "destroy the red cube": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["destroy_red_cube"]],
    },
    "destroy everything": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "reference_object": {
                    "filters": {"selector": {"return_quantity": "ALL"}},
                    "text_span": "everything",
                },
                "action_type": "DESTROY",
            }
        ],
    },
    "destroy the fluff thing": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "DESTROY",
                "reference_object": {
                    "filters": {"triples": [{"pred_text": "has_tag", "obj_text": "fluff"}]}
                },
            }
        ],
    },
    "destroy the fluffy object": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "DESTROY",
                "reference_object": {
                    "filters": {"triples": [{"pred_text": "has_tag", "obj_text": "fluffy"}]}
                },
            }
        ],
    },
}

MOVE_COMMANDS = {
    "move to 42 65 0": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "42 65 0"}}
                },
            }
        ],
    },
    "move to 0 63 0": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "0 63 0"}}
                },
            }
        ],
    },
    "move to -7 63 -8": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "-7 63 -8"}},
                    "text_span": "-7 63 -8",
                },
            }
        ],
    },
    "go between the cubes": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cube"}]}
                    },
                    "relative_direction": "BETWEEN",
                    "text_span": "between the cubes",
                },
            }
        ],
    },
    "move here": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["move_speaker_pos"]],
    },
    "go to the tree": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["go_to_tree"]],
    },
    "move to 20 63 20": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "20 63 20"}},
                    "text_span": "20 63 20",
                },
            }
        ],
    },
    "move_forward": command({"action_type": "MOVE", "location": {"relative_direction": "FRONT"}}),
    "stop": command({"action_type": "STOP"}),
    "move to -7 0 -8": command(
        {
            "action_type": "MOVE",
            "location": {
                "reference_object": {"special_reference": {"coordinates_span": "-7 0 -8"}},
                "text_span": "-7 0 -8",
            },
        }
    ),
    "move to 3 0 2 then 7 0 7": command(
        [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "3 0 2"}},
                    "text_span": "3 0 2",
                },
            },
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "7 0 7"}},
                    "text_span": "7 0 7",
                },
            },
        ]
    ),
    "go between the cubes": command(
        {
            "action_type": "MOVE",
            "location": {
                "reference_object": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cube"}]}
                },
                "relative_direction": "BETWEEN",
                "text_span": "between the cubes",
            },
        }
    ),
    "move here": command(
        {
            "action_type": "MOVE",
            "location": {
                "reference_object": {"special_reference": "SPEAKER"},
                "text_span": "to me",
            },
        }
    ),
    "look at the cube": command(
        {
            "action_type": "DANCE",
            "dance_type": {
                "look_turn": {
                    "location": {
                        "reference_object": {
                            "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cube"}]}
                        },
                        "text_span": "cube",
                    }
                }
            },
        }
    ),
    "go to the cube": command(
        {
            "action_type": "MOVE",
            "location": {
                "reference_object": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cube"}]}
                },
                "text_span": "cube",
            },
        }
    ),
    "get the toy": command(
        {
            "action_type": "GET",
            "reference_object": {
                "filters": {"triples": [{"pred_text": "has_name", "obj_text": "toy"}]}
            },
        }
    ),
}

FILL_COMMANDS = {
    "fill where I am looking": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["fill_speaker_look"]],
    },
    "fill where I am looking with gold": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["fill_speaker_look_gold"]],
    },
    "fill all holes where I am looking": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["fill_all_holes_speaker_look"]],
    },
}

DIG_COMMANDS = {
    "dig a hole": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "schematic": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "hole"}]}
                },
                "action_type": "DIG",
            }
        ],
    }
}


DANCE_COMMANDS = {
    "dance": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "DANCE",
                "dance_type": {
                    "filters": {"triples": [{"pred_text": "has_tag", "obj_text": "dance"}]}
                },
            }
        ],
    }
}

COMBINED_COMMANDS = {
    "build a small sphere then move here": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            INTERPRETER_POSSIBLE_ACTIONS["build_small_sphere"],
            INTERPRETER_POSSIBLE_ACTIONS["move_speaker_pos"],
        ],
    },
    "copy where I am looking to here then build a 1x1x1 cube": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            INTERPRETER_POSSIBLE_ACTIONS["copy_speaker_look_to_agent_pos"],
            INTERPRETER_POSSIBLE_ACTIONS["build_1x1x1_cube"],
        ],
    },
    "move to 3 63 2 then 7 63 7": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "3 63 2"}},
                    "text_span": "3 63 2",
                },
            },
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": {"coordinates_span": "7 63 7"}},
                    "text_span": "7 63 7",
                },
            },
        ],
    },
}

# maybe fixme ACTION_NAME-->NAME ?
GET_MEMORY_COMMANDS = {
    "what is where I am looking": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "memory_type": "REFERENCE_OBJECT",
            "selector": {"location": SPEAKERLOOK},
            "output": {"attribute": "NAME"},
        },
    },
    "what are you doing": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "triples": [{"pred_text": "has_tag", "obj_text": "CURRENTLY_RUNNING"}],
            "memory_type": "TASKS",
            "output": {"attribute": "NAME"},
        },
    },
    "what are you building": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "triples": [
                {"pred_text": "has_tag", "obj_text": "CURRENTLY_RUNNING"},
                {"pred_text": "has_name", "obj_text": "BUILD"},
            ],
            "memory_type": "TASKS",
            "output": {"attribute": {"task_info": {"reference_object": {"attribute": "NAME"}}}},
        },
    },
    "where are you going": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {
                "attribute": {"task_info": {"reference_object": {"attribute": "LOCATION"}}}
            },
            "memory_type": "TASKS",
            "triples": [
                {"pred_text": "has_tag", "obj_text": "CURRENTLY_RUNNING"},
                {"pred_text": "has_name", "obj_text": "MOVE"},
            ],
        },
    },
    "where are you": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "memory_type": "REFERENCE_OBJECT",
            "triples": [{"pred_text": "has_tag", "obj_text": "SELF"}],
        },
    },
    "what is to the left of the cube?": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "memory_type": "REFERENCE_OBJECT",
            "selector": {
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cube"}]}
                    },
                    "relative_direction": "LEFT",
                }
            },
        },
    },
    "how tall is the blue cube?": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "triples": [
                {"pred_text": "has_colour", "obj_text": "blue"},
                {"pred_text": "has_name", "obj_text": "cube"},
            ],
            "output": {"attribute": "HEIGHT"},
        },
    },
    "how wide is the red cube?": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "triples": [
                {"pred_text": "has_colour", "obj_text": "red"},
                {"pred_text": "has_name", "obj_text": "cube"},
            ],
            "output": {"attribute": "WIDTH"},
        },
    },
    "how many cubes are there?": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "COUNT",
            "memory_type": "REFERENCE_OBJECT",
            "triples": [{"pred_text": "has_name", "obj_text": "cube"}],
        },
    },
    "how many blue things are there?": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "triples": [{"pred_text": "has_colour", "obj_text": "blue"}],
            "output": "COUNT",
        },
    },
    "how many blocks are in the blue cube?": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": {"num_blocks": {"block_filters": {}}}},
            "memory_type": "REFERENCE_OBJECT",
            "triples": [
                {"pred_text": "has_name", "obj_text": "cube"},
                {"pred_text": "has_colour", "obj_text": "blue"},
            ],
        },
    },
    "what is the thing closest to you?": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "name"},
            "selector": {
                "return_quantity": {
                    "argval": {
                        "ordinal": "FIRST",
                        "polarity": "MIN",
                        "quantity": {
                            "attribute": {
                                "linear_extent": {
                                    "source": {"reference_object": {"special_reference": "AGENT"}}
                                }
                            }
                        },
                    }
                }
            },
        },
    },
    "what is the thing closest to me?": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "name"},
            "selector": {
                "return_quantity": {
                    "argval": {
                        "ordinal": "FIRST",
                        "polarity": "MIN",
                        "quantity": {
                            "attribute": {
                                "linear_extent": {
                                    "source": {
                                        "reference_object": {"special_reference": "SPEAKER"}
                                    }
                                }
                            }
                        },
                    }
                }
            },
        },
    },
}

PUT_MEMORY_COMMANDS = {
    "that is fluff": {
        "dialogue_type": "PUT_MEMORY",
        "filters": {"selector": {"location": SPEAKERLOOK}},
        "upsert": {
            "memory_data": {
                "memory_type": "TRIPLE",
                "triples": [{"pred_text": "has_tag", "obj_text": "fluff"}],
            }
        },
    },
    "good job": {
        "dialogue_type": "PUT_MEMORY",
        "upsert": {"memory_data": {"memory_type": "REWARD", "reward_value": "POSITIVE"}},
    },
    "that is fluffy": {
        "dialogue_type": "PUT_MEMORY",
        "filters": {"selector": {"location": SPEAKERLOOK}},
        "upsert": {
            "memory_data": {
                "memory_type": "TRIPLE",
                "triples": [{"pred_text": "has_tag", "obj_text": "fluffy"}],
            }
        },
    },
}


def append_output(filt, output):
    new_filt = deepcopy(filt)
    new_filt["output"] = output
    return new_filt


CONDITIONS = {
    "a cow has x greater than 5": {
        "condition_type": "COMPARATOR",
        "condition": {
            "input_left": {
                "value_extractor": {"filters": append_output(FILTERS["a cow"], ATTRIBUTES["x"])}
            },
            "comparison_type": "GREATER_THAN",
            "input_right": {"value_extractor": "5"},
        },
    },
    "that cow has x greater than 5": {
        "condition_type": "COMPARATOR",
        "condition": {
            "input_left": {
                "value_extractor": {"filters": append_output(FILTERS["that cow"], ATTRIBUTES["x"])}
            },
            "comparison_type": "GREATER_THAN",
            "input_right": {"value_extractor": "5"},
        },
    },
    "that cow is closer than 2 steps to me": {
        "condition_type": "COMPARATOR",
        "condition": {
            "input_left": {
                "value_extractor": {
                    "filters": append_output(FILTERS["that cow"], ATTRIBUTES["distance from me"])
                }
            },
            "comparison_type": "LESS_THAN",
            "input_right": {"value_extractor": "2"},
        },
    },
    "2 minutes": {
        "condition_type": "TIME",
        "condition": {
            "comparator": {
                "comparison_measure": "minutes",
                "input_left": {"value_extractor": "NULL"},
                "comparison_type": "GREATER_THAN",
                "input_right": {"value_extractor": "2"},
            }
        },
    },
    "18 seconds": {
        "condition_type": "TIME",
        "condition": {
            "comparator": {
                "comparison_measure": "seconds",
                "input_left": {"value_extractor": "NULL"},
                "comparison_type": "GREATER_THAN",
                "input_right": {"value_extractor": "18"},
            }
        },
    },
}

CONDITIONS["18 seconds after that cow has x greater than 5"] = {
    "condition_type": "TIME",
    "event": CONDITIONS["that cow has x greater than 5"],
    "condition": {
        "comparator": {
            "comparison_measure": "seconds",
            "input_left": {"value_extractor": "NULL"},
            "comparison_type": "GREATER_THAN",
            "input_right": {"value_extractor": "18"},
        }
    },
}


STOP_CONDITION_COMMANDS = {
    "go left until that cow is closer than 2 steps to me": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": "AGENT"},
                    "relative_direction": "LEFT",
                },
                "remove_condition": CONDITIONS["that cow is closer than 2 steps to me"],
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "dig a hole 2 times": {
        "action_sequence": [
            {
                "action_type": "DIG",
                "remove_condition": {
                    "condition_type": "COMPARATOR",
                    "condition": {
                        "comparison_type": "EQUAL",
                        "input_left": {
                            "value_extractor": {
                                "filters": {
                                    "output": {"attribute": "RUN_COUNT"},
                                    "special": {"fixed_value": "THIS"},
                                }
                            }
                        },
                        "input_right": {"value_extractor": "2"},
                    },
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "follow the cow for 2 minutes": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cow"}]}
                    }
                },
                "remove_condition": CONDITIONS["2 minutes"],
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "follow the cow for 18 seconds": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cow"}]}
                    }
                },
                "remove_condition": CONDITIONS["18 seconds"],
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "follow the cow for 18 seconds after it has x greater than 5": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cow"}]}
                    }
                },
                "remove_condition": CONDITIONS["18 seconds after that cow has x greater than 5"],
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "follow the cow until it has x greater than 5": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cow"}]}
                    }
                },
                "remove_condition": CONDITIONS["that cow has x greater than 5"],
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
}


OTHER_COMMANDS = {
    "the weather is good": {"dialogue_type": "NOOP"},
    "stop": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [INTERPRETER_POSSIBLE_ACTIONS["stop"]],
    },
    "undo": {"dialogue_type": "HUMAN_GIVE_COMMAND", "action_sequence": [{"action_type": "UNDO"}]},
}
