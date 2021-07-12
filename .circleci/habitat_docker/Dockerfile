# syntax = docker/dockerfile:experimental
FROM nvidia/cudagl:10.1-base-ubuntu18.04 as base

RUN export DEBIAN_FRONTEND=noninteractive; \
    export DEBCONF_NONINTERACTIVE_SEEN=true; \
    echo 'tzdata tzdata/Areas select Etc' | debconf-set-selections; \
    echo 'tzdata tzdata/Zones/Etc select UTC' | debconf-set-selections; \
    apt-get update -qqy \
    && apt-get install -qqy --no-install-recommends \
       tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN apt update && apt install -y psmisc curl lsb-release sudo


RUN curl 'https://raw.githubusercontent.com/facebookresearch/pyrobot/Develop/robots/LoCoBot/install/locobot_install_all.sh' > locobot_install_all.sh && bash locobot_install_all.sh -t sim_only -p 3 -l interbotix && rm ./locobot_install_all.sh


SHELL ["/bin/bash", "-c"]

#################
# Habitat install
#################

# habitat system deps
RUN apt-get update || true
RUN apt-get install -y --no-install-recommends \
     libjpeg-dev libglm-dev libgl1-mesa-glx libegl1-mesa-dev mesa-utils xorg-dev freeglut3-dev \
     patchelf libbullet-dev


RUN mkdir habitat-test-scenes && cd habitat-test-scenes && wget http://dl.fbaipublicfiles.com/habitat/habitat-test-scenes.zip && \
    unzip habitat-test-scenes.zip && rm habitat-test-scenes.zip

# this was locally put in the directory creating the docker image with select environments from
# the replica dataset: https://github.com/facebookresearch/Replica-Dataset/blob/master/download.sh
ADD ./Replica-Dataset /Replica-Dataset

ADD ./specular.patch specular.patch

RUN git clone https://github.com/facebookresearch/habitat-sim && \
    cd habitat-sim && \
    git checkout eed76b2f3419f3cfbcc6489aa0fe1b69cf89237a && \
    patch -p1 <../specular.patch && \
    . /root/pyenv_pyrobot_python3/bin/activate && . /root/pyrobot_catkin_ws/devel/setup.bash && \
    pip install -r requirements.txt && \
    python setup.py install --headless --with-bullet && \    
    cd .. && rm -rf habitat-sim && \
    git clone https://github.com/facebookresearch/habitat-api && \
    cd habitat-api && \
    git checkout 01696bb10d5735b253691b764286562af87fdbc3 && \
    pip install -e .

RUN patchelf --set-rpath '$ORIGIN' /root/pyenv_pyrobot_python3/lib/python3.6/site-packages/habitat_sim-0.1.4-py3.6-linux-x86_64.egg/habitat_sim/_ext/habitat_sim_bindings.cpython-36m-x86_64-linux-gnu.so

# tested pyrobot commit that works with Habitat
RUN cd ~/low_cost_ws/src/pyrobot && git reset --hard HEAD &&\
    git fetch https://github.com/facebookresearch/pyrobot droidlet/habitat && git checkout droidlet/habitat && \
    . /root/pyenv_pyrobot_python3/bin/activate && . /root/pyrobot_catkin_ws/devel/setup.bash && \
    pip install -e . && \
    pip install -e . && \
    pip install netifaces pyro4 scikit-fmm scikit-image