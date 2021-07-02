"""
This script processes large files eg. templated generations to
create ground truth annotations that are efficient to look up.
"""
import argparse


def remove_duplicates_long_commands_and_NOOPs(
    input_path, output_path, keep_long_commands=False, keep_NOOPs=False
):
    """Remove duplicate commands, NOOPs and long commands in dataset."""
    new_data = {}
    with open(input_path) as fd:
        data = fd.readlines()

    for line in data:
        command, action_dict = line.split("|")
        words_arr = command.split(" ")
        if command in new_data:
            continue
        # Skip long comomands
        if not keep_long_commands and len(words_arr) > 6:
            continue
        # # Skip NOOPs
        if not keep_NOOPs and "NOOP" in line:
            continue
        else:
            new_data[command] = action_dict
    print(len(new_data))

    with open(output_path, "w") as fd:
        for command in new_data:
            fd.write("{}|{}".format(command, new_data[command]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_path",
        type=str,
        help="File we want to process for use in ground truth annotations.",
        # Assuming run from ~/droidlet
        default="agents/craftassist/datasets/full_data/templated.txt",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        help="Where to write ground truth annotations to.",
        default="agents/craftassist/datasets/ground_truth/datasets/templated.txt",
    )
    parser.add_argument(
        "--keep_long_commands",
        default=False,
        action="store_true",
        help="Whether we should keep long commands",
    )
    parser.add_argument(
        "--keep_NOOPs",
        default=False,
        action="store_true",
        help="Whether we should keep commands with NOOPS",
    )
    args = parser.parse_args()
    remove_duplicates_long_commands_and_NOOPs(
        args.input_path, args.output_path, args.keep_long_commands, args.keep_NOOPs
    )
