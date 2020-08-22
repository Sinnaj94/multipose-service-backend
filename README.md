# Motion Capturing API from Single RGB Videos
This is an API which is using openpose and 3d-pose-baseline to
calculate dynamic pose data. Input data is an rgb video with a person.
## Installation
You have to install some prerequisites before using the application.
After that you can begin with the installation of the requirements
### Prerequisites
You will need [python](https://python.org), [pip](https://pypi.org/project/pip/)
as well as [redis](https://redis.io/) installed on your machine.
`python` is the programming language of the API, `pip` is the packet manager
of python and `redis` is used for storing temporal data.
### Installation
First you should create a virtualenvironment for python.
A virtualenvironment is an encapsulated python environment in which
you can install your packages. You should install the requirements 
listed in `requirements.txt` in the virtualenvironment.
1) Create a virtualenvironment using `virtualenv <name>`
2) Activate the virtualenvironment using `source <name>/bin/activate`
3) Install the requirements using `pip install -r requirements.txt`

After that, clone the [openpose](https://github.com/CMU-Perceptual-Computing-Lab/openpose)
and the [3d-pose-baseline](https://github.com/una-dinosauria/3d-pose-baseline) repositories
to some place outside of this repository and build them.


### Running the server
Start the server using
```
FLASK_APP=app.py flask run 
```
## Guidelines
