#!flask/bin/python
import os
import time

import redis
import rq
from rq.job import Job as RedisJob
from rq.exceptions import NoSuchJobError
from flask import Flask, Blueprint, g, jsonify, send_from_directory
from flask.cli import FlaskGroup
from flask_restplus import Api, Resource, abort
from werkzeug.exceptions import HTTPException

from project import parsers

from rq import Queue, Connection
from redis import Redis

# authentication
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth

# initialization
from project.config import Config
from project.conversion_task import convert

app = Flask(__name__)

app_settings = os.getenv("APP_SETTINGS")
app.config.from_object(app_settings)

# extensions
auth = HTTPBasicAuth()

blueprint = Blueprint('api', __name__)
api = Api(app=app,
          version="1.0",
          title="Motion Capturing API",
          description="Motion Capturing Library from single RGB Videos")

app.register_blueprint(blueprint)


# queue building
conn = redis.from_url(app.config["REDIS_URL"])

# import
import project.model.model as model

"""
Status
"""

status_space = api.namespace('status', description='Get the version status of the api')

@status_space.route("/")
class Status(Resource):
    def get(self):
        # REDIS TEST
        return {
            'version': api.version,
            'title': api.title,
            'description': api.description,
            'id': 'motion_capturing_api'
        }

"""
USER MANAGEMENT
"""

user_space = api.namespace('users', description='Users management')

user_parser = api.parser()
user_parser.add_argument('username', type=str, required=True, location='form')
user_parser.add_argument('password', type=str, required=True, location='form')


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@user_space.route("/", endpoint='with-parser')
class CreateUser(Resource):
    @api.expect(user_parser)
    @api.response(409, 'A user with given username already exists')
    @api.response(200, 'User successfully created')
    def post(self):
        args = user_parser.parse_args(strict=True)
        return model.add_user(args['username'], args['password'])


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@user_space.route("/<uuid:id>")
class GetUser(Resource):
    @api.response(404, 'The user with given id does not exist')
    @api.response(200, 'Return user with given id')
    def get(self, id):
        return model.get_user(id)


@user_space.route("/login")
class Login(Resource):
    @auth.login_required
    def get(self):
        return g.user.serialize()


"""
Auth Space
"""

auth_space = api.namespace('auth', description="Authentication")


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@auth.verify_password
def verify_password(username_or_token, password):
    # first try to authenticate by token
    user = model.Users.verify_auth_token(username_or_token)
    if not user:
        # try to authenticate with username/password
        user = model.Users.query.filter_by(username=username_or_token).first()
        if not user or not user.verify_password(password):
            return False
    g.user = user
    return True


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@auth_space.route("/token")
class GetToken(Resource):
    @auth.login_required
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return token which is valid for 600 seconds')
    def get(self):
        # duration in seconds
        duration = 5184000
        # todo: make it longer durable mein lieber
        token = g.user.generate_auth_token(duration)
        print(g.user)
        return jsonify({'exp': time.time() + duration, 'token': token.decode('ascii'), 'duration': duration, 'user': g.user.serialize()})


"""
Jobs Space
"""
jobs_space = api.namespace('jobs', description='Jobs')


class JobRunning(HTTPException):
    code = 202
    description = "Job is pending"


def get_job(id):
    try:
        job = RedisJob.fetch(str(id), connection=conn)
    # if the server was restarted or job not found, it might still be in database
    except NoSuchJobError as e:
        return model.get_job(id)
    if job.is_finished:
        return model.get_job(id)
    else:
        raise JobRunning



@jobs_space.route("/")
class Jobs(Resource):
    """
    Job status
    """
    @auth.login_required
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return all jobs belonging to the authorized user')
    def get(self):
        return model.serialize_array(model.get_jobs_by_user_id(g.user.id))

    @auth.login_required
    @api.expect(parsers.upload_parser)
    @api.doc('get_something')
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return the new job')
    def post(self):
        args = parsers.upload_parser.parse_args()#
        # check if the sent file is actually a video.
        if not args['video'].mimetype == 'video/mp4':
            abort(415)
        with Connection(conn):
            q = Queue()
            task = q.enqueue(convert, video=args['video'].read(), user_id=str(g.user.id))
            return {"job_id" : task.get_id()}


@jobs_space.route("/<uuid:job_id>")
@api.response(401, 'The user is not permitted to do this action')
class Job(Resource):
    """
    Job status
    """

    # get via id
    @auth.login_required
    @api.response(404, 'A job with the given id was not found')
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return the new job')
    def get(self, job_id):
        return get_job(job_id).serialize()


class ResultFailedException(HTTPException):
    code = 404
    description = "Result has failed, hence there is no video"


@jobs_space.route("/<uuid:job_id>/source_video")
class JobSourceVideo(Resource):
    @auth.login_required
    @api.produces(["video/mp4"])
    @api.response(200, 'Return video file')
    def get(self, job_id):
        # check if job exists
        job = get_job(job_id)
        # get the result
        res = model.get_result_by_job_id(job.id)
        # check if result is succesful
        return send_from_directory(res.file_directory, Config.SOURCE_VIDEO_FILE, as_attachment=True,
                                   mimetype="video/mp4")


@jobs_space.route("/<uuid:job_id>/output_video")
class JobOutputVideo(Resource):
    @auth.login_required
    @api.produces(["video/mp4"])
    @api.response(200, 'Return video file')
    def get(self, job_id):
        # check if job exists
        job = get_job(job_id)
        # get the result
        res = model.get_result_by_job_id(job.id)
        # check if result is succesful
        return send_from_directory(res.file_directory, Config.OUTPUT_VIDEO_FILE, as_attachment=True,
                                   mimetype="video/mp4")


def start_job(job_id, **kwargs):
    status = model.start_job(job_id, **kwargs)
    return status


"""
Results Space
"""

results_space = api.namespace('results', description='Results')


@results_space.route("/<uuid:result_id>")
class Result(Resource):
    @auth.login_required
    @api.response(404, 'A result with the given id was not found')
    @api.response(200, 'Return the new job')
    @api.response(401, 'The user is not permitted to do this action')
    def get(self, result_id):
        return model.get_result_by_id(result_id).serialize()


@results_space.route("/")
class Results(Resource):
    @auth.login_required
    @api.response(200, 'Return all the results that match to the given parameters')
    @api.response(401, 'The user is not permitted to do this action')
    @api.expect(parsers.results_parser)
    def get(self):
        args = parsers.results_parser.parse_args()
        return model.serialize_array(model.filter_results(g.user.id, args))


"""
Posts space
"""

posts_space = api.namespace('posts', description='Posts feed')


# return all public posts
@posts_space.route("/")
class Posts(Resource):
    @api.response(200, 'Return the first 100 public posts')
    def get(self):
        return model.serialize_array(model.get_all_public_posts())

# TODO: Put this into "manager"
model.db.init_app(app)
model.db.create_all()