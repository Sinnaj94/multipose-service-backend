from flask import jsonify

from backend import analysis_base
import time
import json
from app import app, enqueue_analysis, db
from model import model

mock_file_3d = "mock_data/ballet.json"
with open(mock_file_3d, 'r') as file:
    mock_data_3d = json.load(file)


def analyse(idle):
    # todo: send to openpose or open-pose-baseline
    print("Starting analysis for %s", str(idle.id))
    idle.status = 3
    db.session.commit()
    time.sleep(10)
    print("Finished analysis for %s", str(idle.id))
    if True:
        idle.output_data = jsonify(mock_data_3d)
        idle.status = 4
        db.session.commit()
    else:
        # todo: fail
        idle.status = -1
        db.session.commit()
    enqueue_analysis()
