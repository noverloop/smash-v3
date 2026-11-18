# openEMS + CSXCAD (current upstream, built from source) with Python bindings.
# Build:  docker build -t smash-openems application/src/smash/sim/antenna/docker
# Used by smash.sim.antenna.openems_runner (it mounts the repo at /repo).
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates pkg-config \
        libhdf5-dev libvtk9-dev libboost-all-dev libcgal-dev libtinyxml-dev \
        libgmp-dev libmpfr-dev \
        python3 python3-dev python3-pip python3-venv cython3 \
        python3-numpy python3-scipy python3-matplotlib python3-h5py python3-setuptools \
    && rm -rf /var/lib/apt/lists/*
ARG OPENEMS_REF=master
RUN git clone --recursive --depth 1 --shallow-submodules -b ${OPENEMS_REF} \
        https://github.com/thliebig/openEMS-Project.git /opt/src/openEMS-Project
WORKDIR /opt/src/openEMS-Project
RUN mkdir build && cd build \
    && cmake .. -DCMAKE_INSTALL_PREFIX=/opt/openEMS -DWITH_MPI=0 -DBUILD_APPCSXCAD=NO \
    && make -j"$(nproc)"
ENV OPENEMS_INSTALL_PATH=/opt/openEMS CSXCAD_INSTALL_PATH=/opt/openEMS \
    LD_LIBRARY_PATH=/opt/openEMS/lib \
    PATH=/opt/openEMS/bin:$PATH
RUN cd CSXCAD/python && OPENEMS_INSTALL_PATH=/opt/openEMS CSXCAD_INSTALL_PATH=/opt/openEMS \
        pip3 install --break-system-packages --no-build-isolation . \
    && cd ../../openEMS/python && OPENEMS_INSTALL_PATH=/opt/openEMS CSXCAD_INSTALL_PATH=/opt/openEMS \
        pip3 install --break-system-packages --no-build-isolation .
RUN python3 -c "import CSXCAD, openEMS; print('openEMS python OK')"
WORKDIR /repo
