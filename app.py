#!flask/bin/python
import os

import time
from flask import Flask, Blueprint, url_for
from flask_restplus import Api, Resource, fields, abort
import json
import uuid
import parsers

from backend import analysis_2d

from rq import Queue
from redis import Redis

app = Flask(__name__)
blueprint = Blueprint('api', __name__)
api = Api(app=app,
          version="1.0",
          title="Motion Capturing API",
          description="Motion Capturing Library from single RGB Videos")

app.register_blueprint(blueprint)


app.config['DATA_FOLDER'] = "."


mock_file_3d = "mock_data/ballet.json"
with open(mock_file_3d, 'r') as file:
    mock_data_3d = json.load(file)


# todo: content type set to video


analysis_2d_space = api.namespace('analysis_2d', description='2D Analysis')

# queue building
redis_conn = Redis()
q = Queue(connection=redis_conn)


@analysis_2d_space.route("/")
class Analysis2DClass(Resource):
    """
    2D Analysis of Video
    """
    # get via id
    def get(self):
        return {
            "status": "Got new data"
        }


# todo: build model
@analysis_2d_space.route("/upload/")
class UploadVideo(Resource):
    @api.expect(parsers.upload_parser)
    def post(self):
        args = parsers.upload_parser.parse_args()
        if args['mp4_file'].mimetype == 'video/mp4':
            destination = os.path.join(app.config.get('DATA_FOLDER'), 'jobs/')
            if not os.path.exists(destination):
                os.makedirs(destination)
            video_id = str(uuid.uuid4())
            mp4_file = '%s%s%s' % (destination, str(video_id),'.mp4')
            args['mp4_file'].save(mp4_file)
        else:
            abort(415)
        return {'status': 'success',
                'analysis_url': url_for("analysis_2d_analyse_video", video_id=video_id),
                'id': video_id}


@analysis_2d_space.route("/analyse/<string:video_id>")
class AnalyseVideo(Resource):
    def get(self, video_id):
        # todo: check if analysis was succesful, return
        return 202

    def post(self, video_id):
        # todo: check if video was already taken in to the queue
        q.enqueue(analysis_2d.analyse_2d, video_id)
        return 202


def do_something_with_file(uploaded_file):
    return True



analysis_model_3d = api.model('3D Analysis Model',
                              {
                                  'data': fields.String(required=True,
                                                        description="2D analysis data",
                                                        help="2D Posing to be analysed in 3D.")
                              },
                              {
                                  'person_id': fields.Integer(required=False,
                                                              description="Person ID",
                                                              help="Give an ID")
                              })

analysis_3d_space = api.namespace('analysis_3d', description='3D Analysis')


@analysis_3d_space.route("/")
class Analysis3DClass(Resource):
    """
    3D Analysis of Data
    """
    @api.expect(analysis_model_3d)
    def post(self):
        # todo: send to 3d-pose-baseline
        return {
            "data": mock_data_3d,
        }, 202

if __name__ == '__main__':
    app.run(debug=True)
