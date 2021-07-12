# syntax = docker/dockerfile:experimental
# FROM nvidia/cudagl:10.1-base-ubuntu18.04 as base
FROM theh1ghwayman/pyrobot-habitat:1.0 as base

RUN apt-get update && apt-get install -y \
    cmake \
    curl \
    g++ \
    clang-format \
    git \
    htop \
    libboost-all-dev \
    libeigen3-dev \
    libgflags-dev \
    libgoogle-glog-dev \
    make \
    python3-dev \
    python3-pip \
    zlib1g-dev 

ENV PATH="/root/miniconda3/bin:${PATH}"
ARG PATH="/root/miniconda3/bin:${PATH}"

RUN apt-get install -y wget && rm -rf /var/lib/apt/lists/*

RUN wget \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    && mkdir /root/.conda \
    && bash Miniconda3-latest-Linux-x86_64.sh -b \
    && rm -f Miniconda3-latest-Linux-x86_64.sh 
RUN conda --version
SHELL ["/bin/bash", "-c"]

# Environment 
ENV GIT_SSH_COMMAND "ssh -i /mcdeploy.key -o StrictHostKeyChecking=no"

RUN conda create -n droidlet_env python=3.7 \
    pytorch==1.7.1 torchvision==0.8.2 \
    cudatoolkit=11.0 -c pytorch && \
    conda init bash && \
    source ~/.bashrc && \
    source activate /root/miniconda3/envs/droidlet_env && \
    curl https://raw.githubusercontent.com/facebookresearch/droidlet/main/requirements.txt -o requirements_1.txt && \
    curl https://raw.githubusercontent.com/facebookresearch/droidlet/main/locobot/requirements.txt -o requirements_2.txt && \
    echo -en '\n' >> requirements_1.txt && \
    tail --lines=+2  requirements_2.txt >> requirements_1.txt && \
    pip install -r requirements_1.txt