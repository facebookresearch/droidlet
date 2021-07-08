#!/bin/bash
# Copyright (c) Facebook, Inc. and its affiliates.

# This script computes hashes for local directories and saves them to data_scripts/default_checksums/
# ./compute_checksum.sh craftassist # hash for semantic parser models
# ./compute_checksum.sh craftassist datasets # hash for datasets folder
# ./compute_checksum.sh locobot # hash for locobot models

function pyabspath() {
    python -c "import os; import sys; print(os.path.realpath(sys.argv[1]))" $1
}

ROOTDIR=$(pyabspath $(dirname "$0")/../../)
echo "Rootdir $ROOTDIR"

. ${ROOTDIR}/tools/data_scripts/checksum_fn.sh --source-only # import checksum function

if [ -z $1 ]
then
    AGENT="craftassist"
    echo "Agent name not specified, defaulting to craftassist"
else
	AGENT=$1
fi

if [ -z $2 ]
then
    HASH_PATH="models"
    echo "Path not specified, defaulting to models/"
else
	HASH_PATH=$2
fi

echo $HASH_PATH
cd ${ROOTDIR}/agents/$AGENT

echo "Computing hashes ..."
if [ "$HASH_PATH" = "models" ]
then
    if [ $AGENT == "locobot" ]; then
        calculate_sha1sum  "${ROOTDIR}/agents/$AGENT/models/perception" "${ROOTDIR}/tools/data_scripts/default_checksums/locobot.txt"
    fi # craftassist
    calculate_sha1sum "${ROOTDIR}/agents/$AGENT/models/semantic_parser" "${ROOTDIR}/tools/data_scripts/default_checksums/nsp.txt"
else # datasets
    calculate_sha1sum "${ROOTDIR}/agents/$AGENT/datasets/" "${ROOTDIR}/tools/data_scripts/default_checksums/datasets.txt"
fi

