FROM cwaffles/openpose AS openpose
WORKDIR /openpose/build/python/openpose
RUN make install

RUN mkdir /usr/local/lib/python3.6/dist-packages/openpose
RUN cp ./pyopenpose.cpython-36m-x86_64-linux-gnu.so /usr/local/lib/python3.6/dist-packages/openpose
WORKDIR /usr/local/lib/python3.6/dist-packages/openpose
RUN ln -s pyopenpose.cpython-36m-x86_64-linux-gnu.so pyopenpose
ENV LD_LIBRARY_PATH=/openpose/build/python/openpose
# python setuptools
RUN apt-get update
RUN apt-get install python3-setuptools -y
RUN apt-get install ffmpeg -y
# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# set final workdir
WORKDIR /usr/src/app

# install dependencies
RUN pip3 install --upgrade pip
COPY requirements.txt /usr/src/app/requirements.txt
RUN pip3 install -r requirements.txt
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# copy project
COPY . /usr/src/app/
