"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import os
import unittest
import json
from ..nsp_querier import NSPQuerier
from droidlet.shared_data_structs import MockOpt
from prettytable import PrettyTable


class fontcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


# NOTE: The following commands in locobot_commands can't be supported
# right away but we'll attempt them in the next round:
# "push the chair",
# "find the closest red thing",
# "copy this motion",
# "topple the pile of notebooks",


common_functional_commands = {
    "turn right": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {"body_turn": {"relative_yaw": {"fixed_value": "-90"}}},
                "action_type": "DANCE",
            }
        ],
    },
    "where are my keys": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}],
        },
    },
    "point at the table": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {
                    "point": {
                        "location": {
                            "reference_object": {
                                "filters": {
                                    "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                                }
                            }
                        }
                    }
                },
                "action_type": "DANCE",
            }
        ],
    },
    "dig two tiny holes there": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {"contains_coreference": "yes"},
                "action_type": "DIG",
                "schematic": {
                    "filters": {
                        "triples": [
                            {"pred_text": "has_name", "obj_text": [0, [3, 3]]},
                            {"pred_text": "has_size", "obj_text": [0, [2, 2]]},
                        ],
                        "selector": {
                            "return_quantity": {"random": [0, [1, 1]]},
                            "same": "ALLOWED",
                        },
                    }
                },
            }
        ],
    },
    "go there": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [{"location": {"contains_coreference": "yes"}, "action_type": "MOVE"}],
    },
    "can you climb on top of the cube": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "relative_direction": "UP",
                    "reference_object": {
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [7, 7]]}]
                        }
                    },
                },
                "action_type": "MOVE",
            }
        ],
    },
    "go to the circle": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "reference_object": {
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                        }
                    }
                },
                "action_type": "MOVE",
            }
        ],
    },
    "what is the name of the yellow shape": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "triples": [{"pred_text": "has_colour", "obj_text": [0, [6, 6]]}],
        },
    },
    "what can you do": {"dialogue_type": "GET_CAPABILITIES", "action_type": "ANY"},
    "what is that blue object": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "triples": [{"pred_text": "has_colour", "obj_text": [0, [3, 3]]}],
            "contains_coreference": "yes",
        },
    },
    "make two red cubes there": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "schematic": {
                    "filters": {
                        "triples": [
                            {"pred_text": "has_name", "obj_text": [0, [3, 3]]},
                            {"pred_text": "has_colour", "obj_text": [0, [2, 2]]},
                        ],
                        "selector": {
                            "return_quantity": {"random": [0, [1, 1]]},
                            "same": "ALLOWED",
                        },
                    }
                },
                "action_type": "BUILD",
                "location": {"contains_coreference": "yes"},
            }
        ],
    },
    "go to the window": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "reference_object": {
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                        }
                    }
                },
                "action_type": "MOVE",
            }
        ],
    },
    "point to the table": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {
                    "point": {
                        "location": {
                            "reference_object": {
                                "filters": {
                                    "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                                }
                            }
                        }
                    }
                },
                "action_type": "DANCE",
            }
        ],
    },
    "look at the table": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {
                    "look_turn": {
                        "location": {
                            "reference_object": {
                                "filters": {
                                    "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                                }
                            }
                        }
                    }
                },
                "action_type": "DANCE",
            }
        ],
    },
    "go left": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "relative_direction": "LEFT",
                    "reference_object": {"special_reference": {"fixed_value": "AGENT"}},
                },
                "action_type": "MOVE",
            }
        ],
    },
    "fill that hole up with sand": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "schematic": {
                    "filters": {
                        "triples": [{"pred_text": "has_block_type", "obj_text": [0, [5, 5]]}]
                    }
                },
                "action_type": "FILL",
                "reference_object": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": [0, [2, 2]]}]},
                    "contains_coreference": "yes",
                },
            }
        ],
    },
    "what size is the table": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "SIZE"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}],
        },
    },
    "what is outside the window": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "selector": {
                "location": {
                    "text_span": [0, [2, 4]],
                    "relative_direction": "OUTSIDE",
                    "reference_object": {
                        "text_span": [0, [4, 4]],
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}]
                        },
                    },
                }
            },
        },
    },
    "follow me": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "remove_condition": {"condition_type": "NEVER"},
                "location": {
                    "reference_object": {"special_reference": {"fixed_value": "SPEAKER"}}
                },
                "action_type": "MOVE",
            }
        ],
    },
    "make a yellow circle to the left of the square": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "schematic": {
                    "filters": {
                        "triples": [
                            {"pred_text": "has_name", "obj_text": [0, [3, 3]]},
                            {"pred_text": "has_colour", "obj_text": [0, [2, 2]]},
                        ]
                    }
                },
                "action_type": "BUILD",
                "location": {
                    "relative_direction": "LEFT",
                    "reference_object": {
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [9, 9]]}]
                        }
                    },
                },
            }
        ],
    },
    "how many red things are there": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "COUNT",
            "triples": [{"pred_text": "has_colour", "obj_text": [0, [2, 2]]}],
        },
    },
    "can you topple the circle": {"dialogue_type": "GET_CAPABILITIES", "action_type": "UNKNOWN"},
    "spawn two pigs": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "SPAWN",
                "reference_object": {
                    "filters": {
                        "triples": [{"pred_text": "has_name", "obj_text": [0, [2, 2]]}],
                        "selector": {
                            "return_quantity": {"random": [0, [1, 1]]},
                            "same": "DISALLOWED",
                        },
                    }
                },
            }
        ],
    },
    "what is to the left of that": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "selector": {
                "location": {
                    "relative_direction": "LEFT",
                    "reference_object": {"filters": {"contains_coreference": "yes"}},
                }
            },
            "memory_type": "REFERENCE_OBJECT",
        },
    },
    "what is to the left of the square": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "selector": {
                "location": {
                    "relative_direction": "LEFT",
                    "reference_object": {
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [7, 7]]}]
                        }
                    },
                }
            },
            "memory_type": "REFERENCE_OBJECT",
        },
    },
    "go to the table": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "reference_object": {
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                        }
                    }
                },
                "action_type": "MOVE",
            }
        ],
    },
    "have you seen my phone": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}],
        },
    },
    "what size is the square": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "SIZE"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}],
        },
    },
    "destroy that": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "action_type": "DESTROY",
                "reference_object": {"filters": {"contains_coreference": "yes"}},
            }
        ],
    },
    "go forward": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "relative_direction": "FRONT",
                    "reference_object": {"special_reference": {"fixed_value": "AGENT"}},
                },
                "action_type": "MOVE",
            }
        ],
    },
    "look at the circle": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {
                    "look_turn": {
                        "location": {
                            "reference_object": {
                                "filters": {
                                    "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                                }
                            }
                        }
                    }
                },
                "action_type": "DANCE",
            }
        ],
    },
    "make a big green square behind me": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "schematic": {
                    "filters": {
                        "triples": [
                            {"pred_text": "has_name", "obj_text": [0, [4, 4]]},
                            {"pred_text": "has_colour", "obj_text": [0, [3, 3]]},
                            {"pred_text": "has_size", "obj_text": [0, [2, 2]]},
                        ]
                    }
                },
                "action_type": "BUILD",
                "location": {
                    "relative_direction": "BACK",
                    "reference_object": {"special_reference": {"fixed_value": "SPEAKER"}},
                },
            }
        ],
    },
    "follow the sheep": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "remove_condition": {"condition_type": "NEVER"},
                "location": {
                    "reference_object": {
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [2, 2]]}]
                        }
                    }
                },
                "action_type": "MOVE",
            }
        ],
    },
    "find the pig": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [2, 2]]}],
        },
    },
    "can you climb on top of the couch": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "relative_direction": "UP",
                    "reference_object": {
                        "filters": {
                            "triples": [{"pred_text": "has_name", "obj_text": [0, [7, 7]]}]
                        }
                    },
                },
                "action_type": "MOVE",
            }
        ],
    },
    "where am i": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "memory_type": "REFERENCE_OBJECT",
            "triples": [{"pred_text": "has_tag", "obj_text": {"fixed_value": "SPEAKER"}}],
        },
    },
    "how many pencils are there": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "COUNT",
            "triples": [{"pred_text": "has_name", "obj_text": [0, [2, 2]]}],
        },
    },
    "what color is the chair": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}],
            "output": {"attribute": "COLOUR"},
        },
    },
    "come here": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [{"location": {"contains_coreference": "yes"}, "action_type": "MOVE"}],
    },
    "where is the picture": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}],
        },
    },
    "make two circles there": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {"contains_coreference": "yes"},
                "action_type": "BUILD",
                "schematic": {
                    "filters": {
                        "triples": [{"pred_text": "has_name", "obj_text": [0, [2, 2]]}],
                        "selector": {
                            "return_quantity": {"random": [0, [1, 1]]},
                            "same": "ALLOWED",
                        },
                    }
                },
            }
        ],
    },
    "show me to the bathroom": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}],
        },
    },
    "point to the jacket": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {
                    "point": {
                        "location": {
                            "reference_object": {
                                "filters": {
                                    "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                                }
                            }
                        }
                    }
                },
                "action_type": "DANCE",
            }
        ],
    },
    "point at the cube": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {
                    "point": {
                        "location": {
                            "reference_object": {
                                "filters": {
                                    "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                                }
                            }
                        }
                    }
                },
                "action_type": "DANCE",
            }
        ],
    },
    "hi": {"dialogue_type": "NOOP"},
    "go back": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "relative_direction": "BACK",
                    "reference_object": {"special_reference": {"fixed_value": "AGENT"}},
                },
                "action_type": "MOVE",
            }
        ],
    },
    "how many cubes are there": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "COUNT",
            "triples": [{"pred_text": "has_name", "obj_text": [0, [2, 2]]}],
        },
    },
    "is there anything big": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "MEMORY",
            "triples": [{"pred_text": "has_size", "obj_text": [0, [3, 3]]}],
        },
    },
    "what color is the square": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "COLOUR"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}],
        },
    },
    "show me to the square": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}],
        },
    },
    "have you seen the pig": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [4, 4]]}],
        },
    },
    "can you topple the chair": {"dialogue_type": "GET_CAPABILITIES", "action_type": "UNKNOWN"},
    "point at the square": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {
                    "point": {
                        "location": {
                            "reference_object": {
                                "filters": {
                                    "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                                }
                            }
                        }
                    }
                },
                "action_type": "DANCE",
            }
        ],
    },
    "what is the name of the thing closest to you": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "selector": {
                "return_quantity": {
                    "argval": {
                        "ordinal": {"fixed_value": "FIRST"},
                        "polarity": "MIN",
                        "quantity": {
                            "attribute": {
                                "linear_extent": {
                                    "source": {
                                        "reference_object": {
                                            "special_reference": {"fixed_value": "AGENT"}
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            },
        },
    },
    "is there anything small": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "MEMORY",
            "triples": [{"pred_text": "has_size", "obj_text": [0, [3, 3]]}],
        },
    },
    "look at the hole": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {
                    "look_turn": {
                        "location": {
                            "reference_object": {
                                "filters": {
                                    "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}]
                                }
                            }
                        }
                    }
                },
                "action_type": "DANCE",
            }
        ],
    },
    "how many yellow things do you see": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "COUNT",
            "triples": [{"pred_text": "has_colour", "obj_text": [0, [2, 2]]}],
        },
    },
    "is there anything red": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "MEMORY",
            "triples": [{"pred_text": "has_colour", "obj_text": [0, [3, 3]]}],
        },
    },
    "where is the circle": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [3, 3]]}],
        },
    },
    "turn left": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "dance_type": {"body_turn": {"relative_yaw": {"fixed_value": "90"}}},
                "action_type": "DANCE",
            }
        ],
    },
    "where are you": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_tag", "obj_text": {"fixed_value": "SELF"}}],
            "memory_type": "REFERENCE_OBJECT",
        },
    },
    "what is the name of the object to my left": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "selector": {
                "location": {
                    "relative_direction": "LEFT",
                    "reference_object": {"special_reference": {"fixed_value": "SPEAKER"}},
                }
            },
        },
    },
    "what is the name of the thing closest to me": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "NAME"},
            "selector": {
                "return_quantity": {
                    "argval": {
                        "ordinal": {"fixed_value": "FIRST"},
                        "polarity": "MIN",
                        "quantity": {
                            "attribute": {
                                "linear_extent": {
                                    "source": {
                                        "reference_object": {
                                            "special_reference": {"fixed_value": "SPEAKER"}
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            },
        },
    },
    "go right": {
        "dialogue_type": "HUMAN_GIVE_COMMAND",
        "action_sequence": [
            {
                "location": {
                    "relative_direction": "RIGHT",
                    "reference_object": {"special_reference": {"fixed_value": "AGENT"}},
                },
                "action_type": "MOVE",
            }
        ],
    },
    "find the hoodie": {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": {"attribute": "LOCATION"},
            "triples": [{"pred_text": "has_name", "obj_text": [0, [2, 2]]}],
        },
    },
}

GROUND_TRUTH_PARSES = {
    "go to the gray chair": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {
                        "filters": {
                            "triples": [
                                {"pred_text": "has_colour", "obj_text": "gray"},
                                {"pred_text": "has_name", "obj_text": "chair"},
                            ]
                        }
                    }
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go to the chair": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "chair"}]}
                    }
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go forward 0.2 meters": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": "AGENT"},
                    "relative_direction": "FRONT",
                    "steps": "0.2",
                    "has_measure": "meters",
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go forward one meter": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": "AGENT"},
                    "relative_direction": "FRONT",
                    "steps": "one",
                    "has_measure": "meter",
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go left 3 feet": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": "AGENT"},
                    "relative_direction": "LEFT",
                    "steps": "3",
                    "has_measure": "feet",
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go right 3 feet": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": "AGENT"},
                    "relative_direction": "RIGHT",
                    "steps": "3",
                    "has_measure": "feet",
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go left 3 meters": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": "AGENT"},
                    "relative_direction": "LEFT",
                    "steps": "3",
                    "has_measure": "meters",
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go forward 1 feet": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": "AGENT"},
                    "relative_direction": "FRONT",
                    "steps": "1",
                    "has_measure": "feet",
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go back 1 feet": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {"special_reference": "AGENT"},
                    "relative_direction": "BACK",
                    "steps": "1",
                    "has_measure": "feet",
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "turn right 90 degrees": {
        "action_sequence": [
            {"action_type": "DANCE", "dance_type": {"body_turn": {"relative_yaw": "-90"}}}
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "turn left 90 degrees": {
        "action_sequence": [
            {"action_type": "DANCE", "dance_type": {"body_turn": {"relative_yaw": "90"}}}
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "turn right 180 degrees": {
        "action_sequence": [
            {"action_type": "DANCE", "dance_type": {"body_turn": {"relative_yaw": "-180"}}}
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "turn right": {
        "action_sequence": [
            {"action_type": "DANCE", "dance_type": {"body_turn": {"relative_yaw": "-90"}}}
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "look at where I am pointing": {
        "action_sequence": [
            {
                "action_type": "DANCE",
                "dance_type": {
                    "look_turn": {
                        "location": {"reference_object": {"special_reference": "SPEAKER_LOOK"}}
                    }
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "wave": {
        "action_sequence": [
            {
                "action_type": "DANCE",
                "dance_type": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "wave"}]}
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "follow the chair": {
        "action_sequence": [
            {
                "action_type": "MOVE",
                "location": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "chair"}]}
                    }
                },
                "remove_condition": {"condition_type": "NEVER"},
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "find Laurens": {
        "action_sequence": [
            {
                "action_type": "SCOUT",
                "reference_object": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "Laurens"}]}
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "bring the cup to Mary": {
        "action_sequence": [
            {
                "action_type": "GET",
                "receiver": {
                    "reference_object": {
                        "filters": {"triples": [{"pred_text": "has_name", "obj_text": "Mary"}]}
                    }
                },
                "reference_object": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "cup"}]}
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
    "go get me lunch": {
        "action_sequence": [
            {
                "action_type": "GET",
                "receiver": {"reference_object": {"special_reference": "SPEAKER"}},
                "reference_object": {
                    "filters": {"triples": [{"pred_text": "has_name", "obj_text": "lunch"}]}
                },
            }
        ],
        "dialogue_type": "HUMAN_GIVE_COMMAND",
    },
}
common_functional_commands.update(GROUND_TRUTH_PARSES)

TTAD_MODEL_DIR = os.path.join(
    os.path.dirname(__file__), "../../../../agents/craftassist/models/semantic_parser/"
)
TTAD_BERT_DATA_DIR = os.path.join(
    os.path.dirname(__file__), "../../../../agents/craftassist/datasets/annotated_data/"
)
GROUND_TRUTH_DATA_DIR = os.path.join(
    os.path.dirname(__file__), "../../../../agents/craftassist/datasets/ground_truth/"
)


def remove_key_text_span(dictionary):
    copy_d = {}
    for key, value in dictionary.items():
        if type(value) == dict and "text_span" in value:
            value.pop("text_span")
            copy_d[key] = value
        else:
            copy_d[key] = value
        if type(value) == dict:
            copy_d[key] = remove_key_text_span(value)
    return copy_d


def remove_text_span(dictionary):
    updated_d = {}
    if dictionary["dialogue_type"] == "HUMAN_GIVE_COMMAND":
        updated_d["action_sequence"] = []
        for action_dict in dictionary["action_sequence"]:
            updated_action_dict = remove_key_text_span(action_dict)
            updated_d["action_sequence"].append(updated_action_dict)
            updated_d["dialogue_type"] = "HUMAN_GIVE_COMMAND"
    else:
        updated_d = remove_key_text_span(dictionary)
    return updated_d


def compare_dicts(dict1, dict2):
    for k, v in dict1.items():
        if k not in dict2:
            return False
        if type(v) == str and dict2[k] != v:
            return False
        if type(v) == list:
            if type(dict2[k]) != list:
                return False
            for val in v:
                # for triples
                if not (val in dict2[k]):
                    return False
        if type(v) == dict:
            if type(dict2[k]) != dict:
                return False
            if not compare_dicts(v, dict2[k]):
                return False
    return True


def compare_full_dictionaries(d1, d2):
    if d1["dialogue_type"] == "HUMAN_GIVE_COMMAND":
        if d2["dialogue_type"] != d1["dialogue_type"]:
            return False
        actions = d1["action_sequence"]
        if len(actions) != len(d2["action_sequence"]):
            return False
        for i, action_dict in enumerate(actions):
            if not compare_dicts(action_dict, d2["action_sequence"][i]):
                return False
        return True
    else:
        return compare_dicts(d1, d2)


class TestDialogueManager(unittest.TestCase):
    def setUp(self) :
        opts = MockOpt()
        opts.nsp_data_dir = TTAD_BERT_DATA_DIR
        opts.ground_truth_data_dir = GROUND_TRUTH_DATA_DIR
        opts.nsp_models_dir = TTAD_MODEL_DIR
        opts.no_ground_truth = False
        self.chat_parser = NSPQuerier(opts)
        self.ground_truth_actions = {}
        print("fetching data from ground truth, from directory: %r" % (opts.ground_truth_data_dir))
        if not opts.no_ground_truth:
            if os.path.isdir(opts.ground_truth_data_dir):
                dataset = opts.ground_truth_data_dir + "datasets/high_pri_commands.txt"
                with open(dataset) as f:
                    for line in f.readlines():
                        text, logical_form = line.strip().split("|")
                        clean_text = text.strip('"').lower()
                        self.ground_truth_actions[clean_text] = json.loads(logical_form)
        self.ground_truth_actions.update(GROUND_TRUTH_PARSES)

    def test_parses(self):
        table = PrettyTable(["Command", "Overall parsing status", "Parsing model status"])
        records = []
        parsing_model_status = False
        pass_cnt, fail_cnt, model_pass_cnt, model_fail_cnt = 0, 0, 0, 0
        for command in common_functional_commands.keys():
            ground_truth_parse = common_functional_commands[command]
            if command in self.ground_truth_actions:
                model_prediction = self.ground_truth_actions[command]
            else:
                # else query the model and remove the value for key "text_span"
                model_prediction = remove_text_span(
                    self.chat_parser.parsing_model.query_for_logical_form(chat=command)
                )

            # compute parsing pipeline accuracy
            status = compare_full_dictionaries(ground_truth_parse, model_prediction)
            if status:
                pass_cnt += 1
                record = [
                    fontcolors.OKGREEN + command + fontcolors.ENDC,
                    fontcolors.OKGREEN + "PASS" + fontcolors.ENDC,
                ]
            else:
                fail_cnt += 1
                record = [
                    fontcolors.FAIL + command + fontcolors.ENDC,
                    fontcolors.FAIL + "FAIL" + fontcolors.ENDC,
                ]
            # compute model correctness status
            model_output = remove_text_span(
                self.chat_parser.parsing_model.query_for_logical_form(chat=command)
            )
            parsing_model_status = compare_full_dictionaries(ground_truth_parse, model_output)
            if parsing_model_status:
                model_pass_cnt += 1
                record += [fontcolors.OKGREEN + "PASS" + fontcolors.ENDC]
            else:
                model_fail_cnt += 1
                record += [fontcolors.FAIL + "FAIL" + fontcolors.ENDC]

            records.append(record)

        for record in records:
            table.add_row(record)
        print(table)

        accuracy = round((pass_cnt / (pass_cnt + fail_cnt)) * 100.0, 2)
        model_accuracy = round((model_pass_cnt / (model_pass_cnt + model_fail_cnt)) * 100.0, 2)
        print_str = (
            fontcolors.OKGREEN
            + "Pass: {} "
            + fontcolors.ENDC
            + fontcolors.FAIL
            + "Fail: {} "
            + fontcolors.ENDC
            + fontcolors.OKCYAN
            + "Parsing pipeline accuracy: {}%"
            + fontcolors.ENDC
        )
        print_model_str = (
            fontcolors.OKGREEN
            + "Pass: {} "
            + fontcolors.ENDC
            + fontcolors.FAIL
            + "Fail: {} "
            + fontcolors.ENDC
            + fontcolors.OKCYAN
            + "Parsing model accuracy: {}%"
            + fontcolors.ENDC
        )
        print(print_str.format(pass_cnt, fail_cnt, accuracy))
        print("Printing Model accuracy status ... ")
        print(print_model_str.format(model_pass_cnt, model_fail_cnt, model_accuracy))
        # check that parsing pipeline is at a 100% accuracy
        self.assertTrue(accuracy == 100.0)


if __name__ == "__main__":
    unittest.main()
