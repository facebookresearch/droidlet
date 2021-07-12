#!/bin/bash
# Copyright (c) Facebook, Inc. and its affiliates.


function pyabspath() {
    python3 -c "import os; import sys; print(os.path.realpath(sys.argv[1]))" $1
}

ROOTDIR=$(pyabspath $(dirname "$0")/../../)
echo "$ROOTDIR"
MODELS_DIRNAME=models_folder

if [ -z $1 ]
then
	AGENT="craftassist"
	echo "Defaulting to default agent: '$AGENT'"
else
	AGENT=$1
fi

if [ -z $2 ]
then
	CHECKSUM_FILE="${ROOTDIR}/tools/data_scripts/default_checksums/nsp.txt"
	CHECKSUM=`cat $CHECKSUM_FILE`  
	echo "Downloading model folder with default checksum from file: '$CHECKSUM_FILE'"
else
	CHECKSUM=$2
fi

echo "Checksum" $CHECKSUM

MODELS_DIRNAME=models_folder

cd $ROOTDIR

echo "====== Downloading http://craftassist.s3-us-west-2.amazonaws.com/pubr/${MODELS_DIRNAME}_${CHECKSUM}.tar.gz to $ROOTDIR/${MODELS_DIRNAME}_${CHECKSUM}.tar.gz ======"
curl http://craftassist.s3-us-west-2.amazonaws.com/pubr/${MODELS_DIRNAME}_${CHECKSUM}.tar.gz -o $MODELS_DIRNAME.tar.gz 

if [ -d "agents/${AGENT}/models" ]
then
	echo "Overwriting models directory"
	rm -rf agents/${AGENT}/models
fi

mkdir -p agents/${AGENT}/models

tar -xzvf $MODELS_DIRNAME.tar.gz -C agents/${AGENT}/models --strip-components 1 || echo "Failed to download and unarchive. Please make sure the file: ${MODELS_DIRNAME}_${CHECKSUM}.tar.gz exists on S3." 

if [[ $AGENT =~ ^(locobot|hello_robot)$ ]]; then
    curl https://locobot-bucket.s3-us-west-2.amazonaws.com/perception_models.tar.gz -o locobot_models.tar.gz
    tar -xzvf locobot_models.tar.gz -C agents/${AGENT}/models

    mkdir -p droidlet/perception/robot/tests/test_assets/
    curl https://locobot-bucket.s3-us-west-2.amazonaws.com/perception_test_assets.tar.gz | tar -xzv -C droidlet/perception/robot/tests/test_assets/
fi
