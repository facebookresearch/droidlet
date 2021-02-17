"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import os
import unittest
import logging

from base_agent.nsp_dialogue_manager import NSPDialogueManager
from base_agent.loco_mc_agent import LocoMCAgent
from base_agent.test.all_test_commands import *
from fake_agent import MockOpt


class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class FakeAgent(LocoMCAgent):
    def __init__(self, opts):
        super(FakeAgent, self).__init__(opts)
        self.opts = opts

    def init_memory(self):
        self.memory = "memory"

    def init_physical_interfaces(self):
        pass

    def init_perception(self):
        pass

    def init_controller(self):
        dialogue_object_classes = {}
        self.dialogue_manager = NSPDialogueManager(self, dialogue_object_classes, self.opts)


# NOTE: The following commands in locobot_commands can't be supported
# right away but we'll attempt them in the next round:
# "push the chair",
# "find the closest red thing",
# "copy this motion",
# "topple the pile of notebooks",
locobot_commands = list(GROUND_TRUTH_PARSES) + [
    "push the chair",
    "find the closest red thing",
    "copy this motion",
    "topple the pile of notebooks",
]

TTAD_MODEL_DIR = os.path.join(os.path.dirname(__file__), "../agent/models/semantic_parser/")
TTAD_BERT_DATA_DIR = os.path.join(os.path.dirname(__file__), "../agent/datasets/annotated_data/")
GROUND_TRUTH_DATA_DIR = os.path.join(os.path.dirname(__file__), "../agent/datasets/ground_truth/")


class TestDialogueManager(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestDialogueManager, self).__init__(*args, **kwargs)
        opts = MockOpt()
        opts.nsp_data_dir = TTAD_BERT_DATA_DIR
        opts.ground_truth_data_dir = GROUND_TRUTH_DATA_DIR
        opts.nsp_models_dir = TTAD_MODEL_DIR
        opts.no_ground_truth = False
        self.agent = FakeAgent(opts)

    def test_parses(self):
        logging.info(
            "Printing semantic parsing for {} locobot commands".format(len(locobot_commands))
        )

        for command in locobot_commands:
            ground_truth_parse = GROUND_TRUTH_PARSES.get(command, None)
            model_prediction = self.agent.dialogue_manager.get_logical_form(
                command, self.agent.dialogue_manager.model
            )

            logging.info(
                "\nCommand -> '{}' \nGround truth -> {} \nParse -> {}\n".format(
                    command, ground_truth_parse, model_prediction
                )
            )

    def test_validate_json(self):
        is_valid_json = self.agent.dialogue_manager.model.validate_parse_tree({})
        self.assertFalse(is_valid_json)



if __name__ == "__main__":
    unittest.main()
