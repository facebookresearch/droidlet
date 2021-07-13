"""
This script collects S3 logs from Turk and postprocesses them

Before running this script, ensure that you have a local copy of turk interactions that are in sync with the S3 directory turk_interactions_with_agent.

See README for instructions.
"""

import glob
import pandas as pd
import re
from datetime import datetime
import argparse
import boto3
import os
import tarfile
import re

pd.set_option("display.max_rows", 10)

def read_s3_bucket(s3_logs_dir, output_dir):
    print("{s3_logs_dir}/**/{csv_filename}".format(s3_logs_dir=s3_logs_dir, csv_filename="logs.tar.gz"))
    # NOTE: This assumes the local directory is synced with the same name as the S3 directory
    pattern = re.compile(".*turk_interactions_with_agent\/([0-9]*)\/(.*)\/logs.tar.gz")
    # NOTE: this is hard coded to search 2 levels deep because of how our logs are structured
    for csv_path in glob.glob('{s3_logs_dir}/**/**/{csv_filename}'.format(s3_logs_dir=s3_logs_dir, csv_filename="logs.tar.gz")):
        tf = tarfile.open(csv_path)
        batch_id = pattern.match(csv_path).group(1)
        timestamp = pattern.match(csv_path).group(2)
        tf.extractall(path="{}/{}/{}/".format(output_dir, batch_id, timestamp))

def read_turk_logs(turk_output_directory, filename):
    # Crawl turk logs directory
    all_turk_interactions = None

    for csv_path in glob.glob("{turk_logs_dir}/**/**/{csv_filename}".format(turk_logs_dir=turk_output_directory, csv_filename=filename + ".csv")):
        print(csv_path)
        with open(csv_path) as fd:
            # collect the NSP outputs CSV
            csv_file = pd.read_csv(csv_path, delimiter="|")
            # add a column with the interaction log ID
            interaction_log_id = re.search(r'\/([^\/]*)\/{}.csv'.format(filename), csv_path).group(1)
            csv_file["turk_log_id"] = interaction_log_id
            if all_turk_interactions is None:
                all_turk_interactions = csv_file
            else:
                all_turk_interactions = pd.concat([all_turk_interactions, csv_file], ignore_index=True)

    # Drop duplicates
    all_turk_interactions.drop_duplicates()
    print(all_turk_interactions.head())
    print(all_turk_interactions.shape)

    # Pipe CSV outputs to another file
    out_path = "{output_dir}/{filename}_{timestamp}.csv".format(output_dir=turk_output_directory, filename=filename, timestamp=datetime.now().strftime("%Y-%m-%d"))
    all_turk_interactions.to_csv(out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # User needs to provide file I/O paths
    parser.add_argument("--turk_logs_directory", help="where to read s3 logs from eg. ~/turk_interactions_with_agent")
    parser.add_argument("--parsed_output_directory", help="where to write the collated NSP outputs eg. ~/parsed_turk_logs")
    parser.add_argument("--filename", default="nsp_outputs", help="name of the CSV file we want to read, eg. nsp_outputs")
    args = parser.parse_args()
    read_s3_bucket(args.turk_logs_directory, args.parsed_output_directory)
    read_turk_logs(args.parsed_output_directory, args.filename)
    