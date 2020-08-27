#!flask/bin/python
import os

import time
from flask import Flask, Blueprint, url_for, g, jsonify
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
app.config['SERVER_NAME'] = "localhost:5000"

app.config['POSTGRESQL_USER'] = my_config['postgresql']['username']
app.config['POSTGRESQL_PASS'] = my_config['postgresql']['password']

# extensions
db = SQLAlchemy(app)
auth = HTTPBasicAuth()

from model import model

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

# queue building
redis_conn = Redis()
q = Queue(connection=redis_conn)

"""
Auth Space
"""

auth_space = api.namespace('auth', description="Authentication")


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@auth.verify_password
def verify_password(username_or_token, password):
    # first try to authenticate by token
    user = model.User.verify_auth_token(username_or_token)
    if not user:
        # try to authenticate with username/password
        user = model.User.query.filter_by(username=username_or_token).first()
        if not user or not user.verify_password(password):
            return False
    g.user = user
    return True


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@auth_space.route("/token")
class GetToken(Resource):
    @auth.login_required
    def get(self):
        token = g.user.generate_auth_token(600)
        print(g.user)
        return jsonify({'token': token.decode('ascii'), 'duration': 600})


"""
Jobs Space
"""
jobs_space = api.namespace('jobs', description='Jobs')

@jobs_space.route("/")
class JobsClass(Resource):
    """
    2D Analysis of Video
    """

    # get via id
    def get(self):
        return {
            "status": "Got new data"
        }


@jobs_space.route("/upload/")
class UploadJob(Resource):
    @auth.login_required
    @api.expect(parsers.upload_parser)
    def post(self):
        args = parsers.upload_parser.parse_args()
        if args['mp4_file'].mimetype == 'video/mp4':
            # todo: Authentication and stuff.
            id = model.add_job(g.user.id)
            destination = app.config.get('VIDEO_JOBS')
            if not os.path.exists(destination):
                os.makedirs(destination)
            mp4_file = os.path.join(destination, '%s%s' %  (str(id), '.mp4'))
            args['mp4_file'].save(mp4_file)
        else:
            abort(415)
        return {'status': 'success',
                'analyse_url': url_for("jobs_start_job", video_id=id),
                'job_id': str(id)}


@jobs_space.route("/start/<uuid:video_id>")
class StartJob(Resource):
    @auth.login_required
    def get(self, video_id):
        # todo : show status
        return 202

    @auth.login_required
    def post(self, video_id):
        return model.start_job(video_id)


@jobs_space.route("/videos/")
class GetVideos(Resource):
    @auth.login_required
    def get(self):
        return model.get_jobs(g.user.id)


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
user_parser.add_argument('username', type=str, required=True, location='form')
user_parser.add_argument('password', type=str, required=True, location='form')


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@user_space.route("/", endpoint='with-parser')
class CreateUser(Resource):
    @api.expect(user_parser)
    def post(self):
        args = user_parser.parse_args(strict=True)
        return model.add_user(args['username'], args['password'])


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@user_space.route("/<uuid:id>")
class GetUser(Resource):
    def get(self, id):
        return model.get_user(id)


if __name__ == '__main__':
    if not os.path.exists('db.sqlite'):
        db.create_all()
    app.run(debug=True)


# with app.app_context():
#     urlvars = False  # Build query strings in URLs
#     swagger = True  # Export Swagger specifications
#     data = api.as_postman(urlvars=urlvars, swagger=swagger)
#     with open("postman_export.json", 'w') as file:
#         json.dump(data, file)
#     file.close()

