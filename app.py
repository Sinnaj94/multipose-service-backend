#!flask/bin/python
import os

import time
from flask import Flask, Blueprint, url_for
from flask_restplus import Api, Resource, fields, abort
import json
import uuid
import parsers

from sqlite3 import OperationalError

from backend import analysis_2d

from rq import Queue
from redis import Redis

from config import my_config

# authentication
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth

# initialization
app = Flask(__name__)

app.config['SECRET_KEY'] = my_config['secret_key']
app.config['SQLALCHEMY_DATABASE_URI'] = my_config['database_uri']
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True

app.config['POSTGRESQL_USER'] = my_config['postgresql']['username']
app.config['POSTGRESQL_PASS'] = my_config['postgresql']['password']

# extensions
db = SQLAlchemy(app)
auth = HTTPBasicAuth()

from model import model_user

blueprint = Blueprint('api', __name__)
api = Api(app=app,
          version="1.0",
          title="Motion Capturing API",
          description="Motion Capturing Library from single RGB Videos")

app.register_blueprint(blueprint)

app.config['VIDEO_JOBS'] = os.path.join(my_config['data_folder'], my_config['analysis_2d_jobs_subfolder'])

# todo: content type set to video

"""
2D SPACE ANALYSIS
"""

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
            destination = app.config.get('VIDEO_JOBS')
            if not os.path.exists(destination):
                os.makedirs(destination)
            video_id = str(uuid.uuid4())
            mp4_file = '%s%s%s' % (destination, str(video_id), '.mp4')
            args['mp4_file'].save(mp4_file)
            # model_2d.add_video(video_id, 'default')
        else:
            abort(415)
        return {'status': 'success',
                'analysis_url': url_for("analysis_2d_analyse_video", video_id=video_id),
                'id': video_id}


@analysis_2d_space.route("/analyse/<string:video_id>")
class AnalyseVideo(Resource):
    def get(self, video_id):
        # todo: check if analysis was successful, return
        """if not model_2d.is_started(video_id):
            return {"message": "2d analysis has not been started yet."
                               "To start the analysis, send a POST request",
                    "analysis_url": url_for("analysis_2d_analyse_video", video_id=video_id)}
        if not model_2d.is_finished(video_id):
            return {"message": "2d analysis is in progress. please wait",
                    "analysis_url": url_for("analysis_2d_analyse_video", video_id=video_id)}, 202"""
        # todo: return data
        return 200

    def post(self, video_id):
        # todo: check if video was already taken in to the queue
        try:
            print("TODO")
            # model_2d.start_analysis(video_id)
        except OperationalError:
            abort(404)
        result = q.enqueue(analysis_2d.analyse_2d, video_id)
        return 202


"""
ANALYSIS 3D OF VIDEO
"""
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
                   "data": "",
               }, 202


"""
USER MANAGEMENT
"""

user_space = api.namespace('users', description='User management')

user_parser = api.parser()
user_parser.add_argument('username', type=str, required=True)
user_parser.add_argument('password', type=str, required=True)


@user_space.route("/", endpoint='with-parser')
class CreateUser(Resource):
    @api.expect(user_parser)
    def post(self):
        args = user_parser.parse_args(strict=True)
        return model_user.add_user(args['username'], args['password'])


if __name__ == '__main__':
    if not os.path.exists('db.sqlite'):
        db.create_all()
    app.run(debug=True)
