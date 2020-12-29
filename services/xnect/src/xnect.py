import os
from ctypes import *
import cv2
import pathlib
import subprocess
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

UPLOAD_FOLDER = "/xnect/videos/"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['FINISHED'] = False
my_status = {}


class InvalidUsage(Exception):
    status_code = 400
    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


# redirect
@app.route("/")
def status():
    """
    Check if xnect container is running
    :return:
    """
    return jsonify({"message": "XNECT running."})


@app.route("/finished")
def finished():
    """
    check if latest job is finished
    :return:
    """
    return jsonify({"finished": app.config['FINISHED']})


@app.route("/<int:id>", methods=['GET', 'POST'])
def analyse(id):
    """
    analyse a video with given id and a video
    """
    if request.method == 'POST':
        print(request.files)
        app.config['FINISHED'] = False
        if 'video' not in request.files:
            print("NO VIDEO")
            return jsonify({"message": "bad request"}), 400
        elif request.files['video'].mimetype != "video/mp4":
            print("WRONG MIMETYPE")
            return jsonify({"message": "bad request"}), 400
        folder = os.path.join(app.config['UPLOAD_FOLDER'], str(id))
        if os.path.isdir(folder):
            return jsonify({"message": "conflict"}), 409
        my_status[str(id)] = False
        os.makedirs(folder)
        file = request.files['video']
        filename = os.path.join(folder, "video.mp4")
        file.save(filename)
        print(folder)
        try:
            # run a subprocess in C++
            subprocess.run("./XNECT " + folder, shell=True, check=True)
            my_status[str(id)] = True
            app.config['FINISHED'] = True
            return jsonify({"message": "success"})
        except subprocess.CalledProcessError as e:
            return jsonify({"code": e.returncode}), 400

    else:
        if str(id) in my_status:
            return jsonify({"status": my_status[str(id)]})
        return jsonify({"message": "not found"}), 404


def get_file(id, filename):
    """
    get a certain file and send it via flask
    :param id:
    :param filename:
    :return:
    """
    folder = os.path.join(app.config['UPLOAD_FOLDER'], str(id))
    return send_from_directory(directory=folder, filename=filename)


@app.route("/<int:id>/ik3d", methods=['GET'])
def get_ik3d(id):
    """
    Get IK3D File
    :param id:
    :return:
    """
    return get_file(id, "IK3D.txt")


@app.route("/<int:id>/ik2d", methods=['GET'])
def get_ik2d(id):
    """
    Get IK2D File
    :param id:
    :return:
    """
    return get_file(id, "IK2D.txt")


@app.route("/<int:id>/raw3d", methods=['GET'])
def get_raw3d(id):
    """
    Get RAW3D File
    :param id:
    :return:
    """
    return get_file(id, "raw3D.txt")


@app.route("/<int:id>/raw2d", methods=['GET'])
def get_raw2d(id):
    """
    Get RAW2D File
    :param id:
    :return:
    """
    return get_file(id, "raw2D.txt")
