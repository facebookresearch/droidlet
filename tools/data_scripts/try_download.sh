#!/bin/bash
# Copyright (c) Facebook, Inc. and its affiliates.

# This script checks if models and datasets are up to date, and downloads default 
# assets (specified in `tool/data_scripts/default_checksums`) if they are stale.

function pyabspath() {
    python3 -c "import os; import sys; print(os.path.realpath(sys.argv[1]))" $1
}

ROOTDIR=$(pyabspath $(dirname "$0")/../../)
echo "Rootdir ${ROOTDIR}"

# Optionally fetch secure resources for internal users and prod systems
python3 ${ROOTDIR}/tools/data_scripts/fetch_internal_resources.py ${ROOTDIR}/droidlet/documents/internal/safety.txt

. ${ROOTDIR}/tools/data_scripts/checksum_fn.sh --source-only # import checksum function

if [ -z $1 ]
then
    AGENT="craftassist"
    echo "Agent name not specified, defaulting to craftassist"
else
    AGENT=$1
fi

AGENT_PATH="${ROOTDIR}/agents/${AGENT}/"
echo "agent path ${AGENT_PATH}"

# in case directories don't even exist, create them
mkdir -p $AGENT_PATH/datasets
mkdir -p $AGENT_PATH/models
mkdir -p $AGENT_PATH/models/semantic_parser
mkdir -p $AGENT_PATH/models/perception

compare_checksum_try_download() {
    LOCAL_CHKSM=$(cat $1)
    FOLDER=$2
    LATEST_CHKSM=$(cat ${ROOTDIR}/tools/data_scripts/default_checksums/${FOLDER}.txt)
    echo "Comparing $FOLDER checksums" 
    echo "Local " $LOCAL_CHKSM
    echo "Latest " $LATEST_CHKSM
    if [[ "$LOCAL_CHKSM" == "$LATEST_CHKSM" ]]; then
        echo "Local $FOLDER directory is up to date."
    else
	    try_download $FOLDER $LATEST_CHKSM
    fi
}

try_download() {
    FOLDER=$1
    CHKSUM=$2
    echo "*********************************************************************************************"
    echo "Local ${FOLDER} directory is out of sync. Downloading latest. Use --dev to disable downloads."
    echo "*********************************************************************************************"
    echo "Downloading ${FOLDER} directory"
    SCRIPT_PATH="$ROOTDIR/tools/data_scripts/fetch_aws_models.sh"
    if cmp -s $FOLDER "datasets"
    then
        SCRIPT_PATH="$ROOTDIR/tools/data_scripts/fetch_aws_datasets.sh"
    fi
    echo "Downloading using script " $SCRIPT_PATH
    "$SCRIPT_PATH" "$AGENT" "$CHKSUM"
}

pushd $AGENT_PATH

# Comparing hashes for local directories
# Default models and datasets shared by all agents
calculate_sha1sum "${AGENT_PATH}models/semantic_parser" "${AGENT_PATH}models/nsp_checksum.txt"
compare_checksum_try_download "models/nsp_checksum.txt" "nsp" 

calculate_sha1sum "${AGENT_PATH}datasets" "${AGENT_PATH}datasets/checksum.txt"
compare_checksum_try_download "${AGENT_PATH}datasets/checksum.txt" "datasets"

# Agent specific models 
if [[ $AGENT =~ ^(locobot|hello_robot)$ ]]; then
    calculate_sha1sum "${AGENT_PATH}models/perception" "${AGENT_PATH}models/locobot_checksum.txt"
    compare_checksum_try_download "${AGENT_PATH}models/locobot_checksum.txt" "locobot"
fi
