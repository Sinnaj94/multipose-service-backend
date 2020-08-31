#!flask/bin/python
import os

from flask import Flask, Blueprint, g, jsonify
from flask.cli import FlaskGroup
from flask_restplus import Api, Resource, abort

from project import parsers

from rq import Queue
from redis import Redis

from project.config import my_config

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

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# extensions
auth = HTTPBasicAuth()

blueprint = Blueprint('api', __name__)
api = Api(app=app,
          version="1.0",
          title="Motion Capturing API",
          description="Motion Capturing Library from single RGB Videos")

app.register_blueprint(blueprint)

app.config['VIDEO_JOBS'] = os.path.join(my_config['data_folder'], my_config['analysis_2d_jobs_subfolder'])

# queue building
redis_conn = Redis()
q = Queue(connection=redis_conn)

# import
from project.backend import analysis
import project.model.model as model

"""
Status
"""

status_space = api.namespace('status', description='Get the version status of the api')

@status_space.route("/")
class Status(Resource):
    def get(self):
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
        token = g.user.generate_auth_token(600)
        print(g.user)
        return jsonify({'token': token.decode('ascii'), 'duration': 600})


"""
Jobs Space
"""
jobs_space = api.namespace('jobs', description='Jobs')


@jobs_space.route("/")
class Jobs(Resource):
    """
    Job status
    """

    # get via id
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
        id = None
        args = parsers.upload_parser.parse_args()
        if args['mp4_file'].mimetype == 'video/mp4':
            # todo: Authentication and stuff.
            id = model.add_job(g.user.id)
            destination = app.config.get('VIDEO_JOBS')
            if not os.path.exists(destination):
                os.makedirs(destination)
            mp4_file = os.path.join(destination, '%s%s' % (str(id), '.mp4'))
            args['mp4_file'].save(mp4_file)
        else:
            abort(415)
        if args['autostart'] is True:
            return start_job(id)
        return {'status': 'posted'}


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
        return model.get_job(job_id).serialize()


def start_job(job_id, **kwargs):
    result = model.start_job(job_id, **kwargs)
    return result.serialize()


@jobs_space.route("/start/<uuid:job_id>")
class StartJob(Resource):
    @auth.login_required
    @api.response(400, 'Bad request')
    @api.response(404, 'A job with the given id was not found')
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return the new result object')
    @api.response(409, 'The result already exists / is pending for the given id')
    @api.response(503, '2D Result does not exist, so 3d analysis can not be started yet')
    @api.expect(parsers.job_start_parser)
    def post(self, job_id):
        args = parsers.job_start_parser.parse_args()
        if args['result_type'] == 0 and args['person_id'] is not None:
            abort(400, "Person id must be null when result_type is set to 0")
        return start_job(job_id, **args)


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


def notify_analysis():
    mdl = model.get_pending_results().first()
    # send to analysis class as json
    if mdl is not None:
        print("yeah")
        test = q.enqueue(analysis.analyse, mdl.id)
    else:
        print("Waiting queue seems to be empty.")


if __name__ == '__main__':
    notify_analysis()
    app.run(debug=False, host='0.0.0.0')
