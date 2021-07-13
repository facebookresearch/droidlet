# Crowdsourcing Tools

This directory contains crowdsourcing pipelines for droidlet.

# Mephisto Setup

Complete the onboarding tutorial at:
https://github.com/facebookresearch/mephisto/blob/master/docs/quickstart.md

This requires you to clone the `Mephisto` repo. You may need to periodically pull updates to `Mephisto` in order to get patches and latest Mephisto features.

## Running the Static HTML workflow
To start a mock task running locally:
`python droidlet_static_html_task/static_test_script.py`

This opens up a task in your browser on localhost, and allows you to view your tasks without MTurk or Heroku credentials. 

## Running Static HTML Tasks with Heroku

### Pre-reqs
You need to have a Heroku account and valid Heroku credentials. To install Heroku CLI on Mac OSX, run `brew tap heroku/brew && brew install heroku`. Then log in with `heroku login` (pass the `-i` flag for validation without browser).

For other installation methods, see https://devcenter.heroku.com/articles/heroku-cli.

You also need an AWS IAM account with MTurk permissions. You also need AWS access keys with permissions to spin up ECS containers, which will be used to communicate with AWS in the flask app. These may or may not be the same access keys; contact your AWS system administrator if you do not have these credentials. 

During the Mephisto onboarding tutorial, you would've configured Mephisto with your AWS credentials. Our Heroku architect pipeline also accesses environment variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`; ensure that these are set.

### Configuring Job Parameters
To configure job parameters, create a file `data.csv` in `droidlet_static_html_task/data.csv`. The header row contains the names of variables, and each row specifies parameters for a single Turk job.

In the Droidlet static task, each turker is given a unique instance of the Voxel world. Currently we pre-launch ECS instances, and set up HTTP/HTTPS proxies for each instance via Cloudflare. Each row in `data.csv` specifies a unique IP. The format of `data.csv` is as follows:

```
subdomain,batch
<IP1>,<batch_id>
<IP2>,<batch_id>
...
```

We can access these template variables directly in the HTML tasks.

### Static Files
To use static resources such as images to your task, you can add them to `droidlet_static_html_task/server_files/extra_refs/`. (This is currently empty, but Mephisto expects this path.)

### Running tasks
Run the following command to start a `droidlet_static_html_task` with `heroku` architect and `flask` server type

```
python droidlet_static_html_task/static_test_script.py mephisto.architect.server_type=flask mephisto/architect=heroku mephisto.architect.server_source_path=<path_to_server>
```

You can replace `droidlet_static_html_task/static_test_script.py` with any mephisto task you would like to run and replace `<path_to_server>` with any heroku server setup you would like to use. For `servermgr` which serves our craftassist.io backend, the code is in `~/droidlet/crowdsourcing/servermgr`.

### Running tasks with Onboarding
The onboarding workflow is as follows:
1. Turk worker accepts task. If the Turk worker has completed and passed this onboarding flow before, the worker is auto-approved. If the worker failed this task before, the worker is denied. Otherwise, the Turker must do the onboarding task.
2. New Turker is shown onboarding task with instructions that are almost identical to the setup of the main task, eg. including bot capabilities and what is allowed/disallowed and encouraged. In the free form onboarding flow, worker is asked to write up to N instructions for the robot assistant in a text box.
3. On form submit, the response is processed and we run a series of checks to validate the quality of interactions: number of commands, richness, diversity. Onboarding tasks are only successful if they pass all these checks.
4. Turk worker success or failure is recorded in Mephisto DB, and successful workers are taken to the primary task.


Run the following command to start a `droidlet_static_html_task` with onboarding using the `local` architect:
```
python droidlet_static_html_task/static_run_with_onboarding.py mephisto/architect=local
```
Make sure port 3000 is tunneled on your mac.

Run the following command to run the above in the MTurk sandbox.
```
python droidlet_static_html_task/static_run_with_onboarding.py mephisto/architect=heroku mephisto.provider.requester_name=[username]_sandbox
```
You will need to log into your MTurk account if you are not already logged in.

Note that currently the onboarding flow does not work with the `flask` server type, so we use the default `node` server type in Mephisto.

## Extra configs for using servermgr
This section is for workflows that deploy an external server. This is currently not necessary for our Droidlet dashboard task runs if ECS instances are pre-launched and IPs are passed into Turk tasks via Mephisto configs.

Since we are requesting ECS instance in servermgr flask app. It's required to set up aws-specific information as environment variable passed to heroku. Make sure the following hydra variables are set in your mephisto config file in `conf/example.yaml`:

```
mephisto:
  architect:
    heroku_app_name: YOUR_HEROKU_APP_NAME
    heroku_config_args:
      AWS_ACCESS_KEY_ID: XXX
      AWS_SECRET_ACCESS_KEY: XXX
      AWS_DEFAULT_REGION: XXX (should be "us-west-1")
```

### Processing S3 Logs

To maintain a local copy of interaction logs stored in S3, run

```
aws s3 sync s3://craftassist/turk_interactions_with_agent/turk/ ~/turk_interactions_with_agent
```

This creates a local directory `turk_interactions_with_agent` that contains all the files in the S3 path. You will need to run this periodically to fetch updates when Turk tasks complete and logs are uploaded.

Assuming you have a local directory synced to the S3 path, you can process the logs by running `process_s3_logs.py`.

This script will traverse the S3 logs directory and untar the tar files, then read all the CSV files for a given type of interaction, deduplicate and clean data, and write the output to a given location. 

