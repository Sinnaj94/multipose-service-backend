import os
from ctypes import *
import pathlib
import subprocess
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

UPLOAD_FOLDER = "/xnect/videos/"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
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
    return jsonify({"message": "XNECT running."})


@app.route("/<uuid:id>", methods=['GET', 'POST'])
def analyse(id):
    if request.method == 'POST':
        print(request.files)
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
            subprocess.run("./XNECT " + folder, shell=True, check=True)
            my_status[str(id)] = True
            return jsonify({"message": "success"})
        except subprocess.CalledProcessError as e:
            return jsonify({"code": e.returncode}), 400

    else:
        if str(id) in my_status:
            return jsonify({"status": my_status[str(id)]})
        return jsonify({"message": "not found"}), 404


def get_file(id, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], str(id))
    return send_from_directory(directory=folder, filename=filename)


@app.route("/<uuid:id>/ik3d", methods=['GET'])
def get_ik3d(id):
    return get_file(id, "IK3D.txt")


@app.route("/<uuid:id>/ik2d", methods=['GET'])
def get_ik2d(id):
    return get_file(id, "IK2D.txt")


@app.route("/<uuid:id>/raw3d", methods=['GET'])
def get_raw3d(id):
    return get_file(id, "raw3D.txt")


@app.route("/<uuid:id>/raw2d", methods=['GET'])
def get_raw2d(id):
    return get_file(id, "raw2D.txt")
