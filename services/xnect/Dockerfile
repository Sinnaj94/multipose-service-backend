FROM nvidia/cuda:9.1-cudnn7-devel

# install base requirements
WORKDIR /
RUN apt-get update && \
DEBIAN_FRONTEND=noninteractive apt-get install -y \
cmake nano git qt5-default libboost-all-dev autoconf autogen libhdf5-dev liblmdb-dev libsnappy-dev wget libatlas-base-dev libgflags-dev libgoogle-glog-dev liblmdb-dev python-pip libprotobuf-dev protobuf-compiler python-dev libxml2-dev libxslt-dev ffmpeg pkg-config libav-tools libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libx264-dev

# install leveldb
WORKDIR /tmp
ARG LEVEL_DB_VERSION
RUN echo ${LEVEL_DB_VERSION}
RUN wget https://github.com/google/leveldb/archive/v${LEVEL_DB_VERSION}.tar.gz
RUN tar xvf v${LEVEL_DB_VERSION}.tar.gz
RUN rm -f v${LEVEL_DB_VERSION}.tar.gz

WORKDIR /tmp/leveldb-${LEVEL_DB_VERSION}
RUN make
RUN scp -r out-static/lib* out-shared/lib* "/usr/local/lib"
WORKDIR /tmp/leveldb-${LEVEL_DB_VERSION}/include
RUN scp -r leveldb /usr/local/include
RUN ldconfig

# install protobuf
WORKDIR /
RUN git clone https://github.com/protocolbuffers/protobuf --recursive
WORKDIR /protobuf

RUN ./autogen.sh
RUN ./configure CFLAGS="-fPIC" CXXFLAGS="-fPIC"
RUN make
RUN make install

# install opencv with modules
WORKDIR /
RUN git clone -b 3.4 https://github.com/opencv/opencv

# checkout opencv version
RUN git clone -b 3.4 https://github.com/opencv/opencv_contrib


WORKDIR /opencv/build
RUN cmake -D CMAKE_BUILD_TYPE=RELEASE -D CMAKE_INSTALL_PREFIX=/usr/lib -D WITH_TBB=ON -D BUILD_NEW_PYTHON_SUPPORT=ON -D WITH_V4L=ON -D WITH_QT=ON -D WITH_OPENGL=ON -D BUILD_TIFF=ON -D_GLIBCXX_USE_CXX11_ABI=0 -D OPENCV_EXTRA_MODULES_PATH=/opencv_contrib/modules/ -DWITH_FFMPEG=1 ..
RUN make -j8
RUN make install

WORKDIR /
RUN pip install numpy==1.14.0
RUN git clone https://github.com/Sinnaj94/caffe
WORKDIR /caffe/build
# ldconfig refreshes cache
RUN ldconfig
RUN cmake -DOpenCV_DIR=/usr/lib/share/OpenCV/ -DCMAKE_CXX_FLAGS='-std=c++11' ..

RUN protoc --version
RUN make -j 8


WORKDIR /xnect
COPY ./xnect_library/ /xnect/
COPY ./src/ /xnect/src/
RUN apt update
RUN apt install python3 python3-pip -y
RUN pip3 install --upgrade pip
WORKDIR /xnect/src/
RUN pip3 install -r requirements.txt
WORKDIR /xnect/build
# clear cache
ENV CPLUS_INCLUDE_PATH="$CPLUS_INCLUDE_PATH:/usr/include/python2.7/"
RUN cmake -DOpenCV_DIR=/usr/lib/share/OpenCV  -DCaffe_DIR=/caffe/build -DCMAKE_BUILD_TYPE=Release ..
RUN make clean
RUN make -j8
WORKDIR /xnect/bin/Release
COPY ./src/xnect.py /xnect/bin/Release/xnect.py
ENV LANG C.UTF-8
ENV LANG C.UTF-8
# TODO: REMOVE THAT
ENV FLASK_ENV development
ENV FLASK_DEBUG 1
ENV FLASK_APP xnect.py

