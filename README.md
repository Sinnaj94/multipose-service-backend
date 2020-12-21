# Motion Capturing API from Single RGB Videos
This is an API which is using openpose and 3d-pose-baseline to
calculate dynamic pose data. Input data is a rgb video.
## Hardware
You need a graphics card with CUDA-Support for the calculations.
## Requisites
This repository has been fully tested on [Ubuntu 20.04](https://releases.ubuntu.com/20.04/).
It might also work on other Environments, but you may need different installation steps to make it run.

### Installing the NVIDIA driver
First of all, you should install an NVIDIA driver with support for CUDA >10.0.
It is recommended to get the newest driver from the [NVIDIA site](https://www.nvidia.de/Download/index.aspx) and install it.
In Ubuntu, you can install the driver using *Software Update*, but this didn't work for me.
You don't need to install the CUDA toolkit yet, the Docker Image will take care of that
([more info on this page](https://github.com/NVIDIA/nvidia-docker)).
### Installing docker
This image is heavily relying on the benefits of the software [Docker](https://www.docker.com/).
You must install it on your local machine. 
#### docker-compose Extension
Unfortunately, you have to do an easy manual extension of the *docker-compose*-ecosystem.
This step is very important, because otherwise, the `docker-compose` commands will not be available for this repository.

It is a [widely known issue](https://github.com/docker/compose/issues/6691), that the NVIDIA toolkit is not integrated into `docker-compose` files yet.
Follow the steps of *Installation* from the repository https://github.com/NVIDIA/nvidia-container-runtime to make it work.
### Downloading the 3D models
The *openpose* images come with docker, so you don't have to take care of that.
Nonetheless, you have to download the right models for 3d evaluation and put them into the [3d_models](services/web/3d_models) folder.

The models are not mine, they are from the following repository: https://github.com/KevinLTT/video2bvh.
They can be downloaded from [Google Drive](https://drive.google.com/drive/folders/1M2s32xQkrDhDLz-VqzvocMuoaSGR1MfX).

You only have to download the `openpose_video_pose_243f` folder and extract the files `best_58.58.pth` and `video_pose.yaml`
directly into the [services/web/3d_models](services/web/3d_models) folder.
## Configuration
### Security
:warning: If you are planning on running this app on production, it is important to change the keys
to *secure strings*.
#### PostgreSQL
From [docker-compose.yml](docker-compose.yml):
```
environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=CHANGE_THIS_TO_A_STRONG_PASSWORD
      - POSTGRES_DB=mocap
```
From [.env.dev](.env.dev):
```
DATABASE_URL=postgresql://user:CHANGE_THIS_TO_A_STRONG_PASSWORD@db:5432/mocap
```
#### Flask
From [.env.dev](.env.dev): 
```
SECRET_KEY=CHANGE_THIS_KEY
```

### App Settings
The Server Settings can be accessed in file [config.py](services/web/project/config.py).

## Running
Running this repository is fairly easy. You just have to type `docker-compose build` to build the image and `docker-compose up`
to run the application. Docker will take care of creating and managing the containers and installing all the requirements.
If an error occurs, it is probably due to a wrong NVIDIA-CUDA-Docker configuration.
Please refer to [docker-compose Extension](#docker-compose-Extension) to fix that error.
## Working with the api
If everything works, your API will be accessible at [127.0.0.1 (localhost)](127.0.0.1).
All methods are descripted using a swagger documentation.

The Methods are also listed in the wiki.
## References
- [video2bvh](https://github.com/KevinLTT/video2bvh) by KevinLTT
- [openpose](https://github.com/CMU-Perceptual-Computing-Lab/openpose) by CMU-Perceptual-Computing-Lab
- [openpose Docker image](https://hub.docker.com/r/cwaffles/openpose) by cwaffles