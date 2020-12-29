# get the python base image and install requirements
FROM python
RUN apt-get update
RUN apt-get install python3-setuptools -y
RUN apt-get install ffmpeg -y
# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# set final workdir
WORKDIR /usr/src/app

# install dependencies (via pip package manager)
RUN pip3 install --upgrade pip
COPY requirements.txt /usr/src/app/requirements.txt
RUN pip3 install -r requirements.txt
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
RUN pip3 install opencv-python
# copy project
COPY . /usr/src/app/
