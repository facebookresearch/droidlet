#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import gzip
import logging
import os
import random
import socket
import time
import CloudFlare
import csv

from base64 import b64encode, b64decode
from datetime import datetime, timezone

import boto3

import ping_cuberite

AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
AWS_DEFAULT_REGION = os.environ["AWS_DEFAULT_REGION"]

ec2 = boto3.resource("ec2")
ecs = boto3.client(
    "ecs", aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)
s3 = boto3.resource("s3")

logging.basicConfig(format="%(asctime)s [%(levelname)s]: %(message)s")
logging.getLogger().setLevel(logging.INFO)

SUBNET_IDS = ["subnet-bee9d9d9"]
SECURITY_GROUP_IDS = ["sg-04ec8fa6e1d91d460"]

with open("run.withagent.sh", "rb") as f:
    txt = f.read()
    txt_flat = txt.replace(b"diverse_world", b"flat_world")
    run_sh_gz_b64 = b64encode(gzip.compress(txt)).decode("utf-8")
    run_flat_sh_gz_b64 = b64encode(gzip.compress(txt_flat)).decode("utf-8")


def launch_instance(task="craftassist", config="random", debug=False):
    """Returns instance id (specifically, ECS task ARN) of a newly launched instance.

    Instance is not yet ready, and may not even have an ip address assigned!
    """

    if config == "diverse_world":
        run_sh = run_sh_gz_b64
    elif config == "flat_world":
        run_sh = run_flat_sh_gz_b64
    elif config == "random":
        run_sh = random.choice([run_sh_gz_b64, run_flat_sh_gz_b64])
    else:
        raise ValueError("Bad config={}".format(config))

    timestamp = datetime.now(timezone.utc).isoformat()
    r = ecs.run_task(
        cluster="craftassist",
        taskDefinition=task,
        count=1,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": SUBNET_IDS,
                "securityGroups": SECURITY_GROUP_IDS,
                "assignPublicIp": "ENABLED",
            }
        },
        overrides={
            "containerOverrides": [
                {
                    "name": "craftassist",
                    "environment": [
                        {"name": "RUN_SH_GZ_B64", "value": run_sh},
                        {"name": "AWS_ACCESS_KEY_ID", "value": AWS_ACCESS_KEY_ID},
                        {"name": "AWS_SECRET_ACCESS_KEY", "value": AWS_SECRET_ACCESS_KEY},
                        {"name": "TIMESTAMP", "value": timestamp},
                        {
                            "name": "SENTRY_DSN",
                            "value": os.environ.get("CRAFTASSIST_SENTRY_DSN", ""),
                        },
                        {"name": "CLOUDFLARE_TOKEN", "value": os.getenv("CLOUDFLARE_TOKEN")},
                        {"name": "CLOUDFLARE_ZONE_ID", "value": os.getenv("CLOUDFLARE_ZONE_ID")},
                    ],
                }
            ]
        },
    )
    logging.info("Launched: {}".format(r))
    return r["tasks"][0]["taskArn"], timestamp


def is_instance_up(instance_id):
    try:
        x = ecs.describe_tasks(cluster="craftassist", tasks=[instance_id])

        attachment_id = x["tasks"][0]["containers"][0]["networkInterfaces"][0]["attachmentId"]
        attachment = next(y for y in x["tasks"][0]["attachments"] if y["id"] == attachment_id)

        eni = next(y for y in attachment["details"] if y["name"] == "networkInterfaceId")["value"]
        ip = ec2.NetworkInterface(eni).private_ip_addresses[0]["Association"]["PublicIp"]

        s = socket.socket()
        s.settimeout(10)
        s.connect((ip, 25565))
        s.close()

        ping_cuberite.ping(ip, 25565, timeout=1)

    except:
        return False

    return True


def get_instance_ip(instance_id):
    try:
        x = ecs.describe_tasks(cluster="craftassist", tasks=[instance_id])

        attachment_id = x["tasks"][0]["containers"][0]["networkInterfaces"][0]["attachmentId"]
        attachment = next(y for y in x["tasks"][0]["attachments"] if y["id"] == attachment_id)

        eni = next(y for y in attachment["details"] if y["name"] == "networkInterfaceId")["value"]
        ip = ec2.NetworkInterface(eni).private_ip_addresses[0]["Association"]["PublicIp"]
    except:
        raise ValueError(f'This instance {instance_id} should have been up, but failed to get ip')
    return ip

    
def request_instance(instance_num):
    logging.info(f"Requesting {instance_num} instances from AWS")
    instances = [launch_instance(task="craftassist", config="flat_world", debug=False)[0] for _ in range(instance_num)]
    instance_status = [False] * instance_num

    while not all(instance_status):
        time.sleep(5)
        logging.info(f"Checking status of {instance_num} instances... Not ready!")
        for i in range(instance_num):
            instance_status[i] = is_instance_up(instances[i])
    
    instance_ips = [get_instance_ip(instance) for instance in instances]
    logging.info(f"All {instance_num} are up, ip list: {instance_ips}")
    return instance_ips


def register_dashboard_subdomain(cf, zone_id, ip, subdomain):
    """Registers a unique subdomain for craftassist.io
    that serves proxied HTTP content using cloudflare.
    Args:
    cf -- CloudFlare context with R/W permissions.
    zone_id -- zone ID used to locate DNS records.
    ip -- IP of the ECS container that runs dashboard.
    subdomain -- subdomain contains a unique identifier for this task run, 
    which is the batch ID concatenated with the run number.
    """
    # Check that DNS record does not already exist
    dns_record_exists = cf.zones.dns_records.get(
        zone_id, params={"name": "{}.craftassist.io".format(subdomain)}
    )
    if dns_record_exists:
        print("DNS record already exists for {}".format(subdomain))
        return

    dns_record = {"name": subdomain, "type": "A", "content": ip, "proxied": True}
    try:
        r = cf.zones.dns_records.post(zone_id, data=dns_record)   
        print("Registered IP {} at subdomain {}".format(ip, subdomain))
    except Exception as e:
        raise e 

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance_num", type=int, default=1, help="number of instances requested")
    parser.add_argument("--batch_id", type=int, default=0, help="ID of the current batch, used to track which group of runs the task was run in")
    parser.add_argument("--user", type=str, default="rebeccaqian@fb.com", help="Email of the CloudFlare account")
    args = parser.parse_args()
    instance_ips = request_instance(args.instance_num)
    # register subdomain to proxy instance IP
    if os.getenv("CLOUDFLARE_TOKEN") and os.getenv("CLOUDFLARE_ZONE_ID"):
        logging.info("registering subdomains on craftassist.io")
        cloudflare_token = os.getenv("CLOUDFLARE_TOKEN")
        zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
        cf = CloudFlare.CloudFlare(email=args.user, token=cloudflare_token)
        dns_records = cf.zones.dns_records.get(zone_id)

        # Write the subdomains and batch IDs to input CSV for Mephisto
        # CSV file headers
        headers = ["subdomain", "batch"]
        with open("../droidlet_static_html_task/data.csv", "w") as fd:
            csv_writer = csv.writer(fd, delimiter=",")
            csv_writer.writerow(headers)
            for x in range(len(instance_ips)):
                ip = instance_ips[x]
                subdomain = "dashboard-{}-{}".format(args.batch_id, x)
                register_dashboard_subdomain(cf, zone_id, ip, subdomain)
                # Write record to Mephisto task input CSV
                csv_writer.writerow([subdomain, args.batch_id])
