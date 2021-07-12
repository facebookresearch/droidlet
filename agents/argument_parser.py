"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import argparse
import os


class ArgumentParser:
    def __init__(self, agent_type, base_path):
        self.agent_parsers = {
            "Minecraft": self.add_mc_parser, "Locobot": self.add_loco_parser
        }
        self.base_path = base_path
        self.parser = argparse.ArgumentParser()

        # NSP args
        self.add_nsp_parser()

        # Agent specific args
        self.agent_parsers[agent_type]()

        self.parser.add_argument(
            "--log_level",
            "-log",
            default="info",
            choices=["info", "debug", "warn", "error"],
            help="Logging tier to specify verbosity level, eg. DEBUG.",
        )
        self.parser.add_argument(
            "--no_default_behavior",
            action="store_true",
            help="do not perform default behaviors when idle",
        )
        self.parser.add_argument(
            "--verify_hash_script_path",
            default="../../tools/data_scripts/try_download.sh",
            help="path to script that checks hash against latest models and tries download",
        )
        self.parser.add_argument(
            "--agent_debug_mode",
            action="store_true",
            default=False,
            help="Support a mode where the agent fails gracefully. Only use this for turk session, etc. ",
        )
        self.parser.add_argument(
            "--log_timeline",
            action="store_true", 
            default=False,
            help="enables timeline logging for dashboard",
        )
        self.parser.add_argument(
            "--enable_timeline",
            action="store_true", 
            default=False,
            help="enables the dashboard timeline to display events",
        )

    def add_nsp_parser(self):
        nsp_parser = self.parser.add_argument_group("Neural Semantic Parser Args")

        nsp_parser.add_argument(
            "--model_base_path",
            default="#relative",
            help="if empty model paths are relative to this file",
        )
        nsp_parser.add_argument(
            "--nsp_models_dir",
            default="models/semantic_parser/",
            help="path to semantic parsing models",
        )
        nsp_parser.add_argument(
            "--nsp_data_dir", default="datasets/annotated_data/", help="path to annotated data"
        )
        nsp_parser.add_argument(
            "--ground_truth_data_dir",
            default="datasets/ground_truth/",
            help="path to folder of common short and templated commands",
        )
        nsp_parser.add_argument(
            "--no_ground_truth",
            action="store_true",
            default=False,
            help="do not load from ground truth",
        )
        nsp_parser.add_argument(
            "--dev",
            action="store_true",
            default=False,
            help="Run the agent without automatic model/dataset downloads. Useful for testing models locally.",
        )

    def add_mc_parser(self):
        mc_parser = self.parser.add_argument_group("Minecraft Agent Args")
        mc_parser.add_argument(
            "--semseg_model_path", default="", help="path to semantic segmentation model"
        )
        mc_parser.add_argument(
            "--geoscorer_model_path", default="", help="path to geoscorer model"
        )
        mc_parser.add_argument("--port", type=int, default=25565)

    def add_loco_parser(self):
        loco_parser = self.parser.add_argument_group("Locobot Agent Args")
        IP = "192.168.1.244"
        if os.getenv("LOCOBOT_IP"):
            IP = os.getenv("LOCOBOT_IP")
            print("setting default locobot ip from env variable LOCOBOT_IP={}".format(IP))
        loco_parser.add_argument("--ip", default=IP, help="IP of the locobot")
        loco_parser.add_argument(
            "--incoming_chat_path", default="incoming_chat.txt", help="path to incoming chat file"
        )
        loco_parser.add_argument("--backend", default="habitat")
        loco_parser.add_argument(
            "--perception_model_dir",
            default="models/perception/",
            help="path to perception model data dir",
        )
        loco_parser.add_argument(
            "--check_controller",
            action="store_true",
            help="sanity checks the robot's movement, camera, arm.",
        )

    def fix_path(self, opts):
        if opts.model_base_path == "#relative":
            base_path = self.base_path
        else:
            base_path = opts.model_base_path
        od = opts.__dict__
        for optname, optval in od.items():
            if "path" in optname or "dir" in optname:
                if optval:
                    od[optname] = os.path.join(base_path, optval)
        return opts

    def parse(self):
        opts = self.parser.parse_args()
        return self.fix_path(opts)
