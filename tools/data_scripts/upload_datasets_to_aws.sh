#!/bin/bash
# Copyright (c) Facebook, Inc. and its affiliates.

# This script creates a tar and hash of the datasets directory.
# If uploading files to S3 through console UI, go to the web interface at: 
# https://s3.console.aws.amazon.com/s3/buckets/craftassist?region=us-west-2&prefix=pubr/&showversions=false 
# and upload ``datasets_folder_<sha1sum>.tar.gz``.

function pyabspath() {
    python -c "import os; import sys; print(os.path.realpath(sys.argv[1]))" $1
}

ROOTDIR=$(pyabspath $(dirname "$0")/../../)
echo "$ROOTDIR"
. ${ROOTDIR}/tools/data_scripts/checksum_fn.sh --source-only

if [ -z $1 ]
then
    AGENT="craftassist"
    echo "Agent name not specified, defaulting to craftassist"
else
	AGENT=$1
fi

AGENT_PATH="${ROOTDIR}/agents/${AGENT}/"
echo "$AGENT_PATH"

DIRNAME="datasets"

cd $AGENT_PATH
CHECKSUM_PATH="${DIRNAME}/checksum.txt"
calculate_sha1sum "${AGENT_PATH}${DIRNAME}" "${AGENT_PATH}${CHECKSUM_PATH}"

CHKSUM=$(cat $CHECKSUM_PATH)
echo "CHECKSUM" $CHKSUM

tar -czvf ${DIRNAME}_folder_${CHKSUM}.tar.gz --exclude='*/\.*' --exclude='*checksum*' ${DIRNAME}/

read -p "Do you want to upload ${DIRNAME}_folder_${CHKSUM}.tar.gz to S3 ? " -n 1 -r
if [[ $REPLY =~ ^[Yy]$ ]]
then
    echo "Uploading ..."
    aws s3 cp ${DIRNAME}_folder_${CHKSUM}.tar.gz s3://craftassist/pubr/
fi