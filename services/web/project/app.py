#!flask/bin/python
import enum
import io
import os
import pathlib
import time
import zipfile

import redis
from flask_restplus.fields import Raw
from rq.job import Job as RedisJob
from rq.exceptions import NoSuchJobError
from flask import Flask, Blueprint, g, jsonify, send_from_directory, url_for, make_response, render_template, redirect, \
    send_file
from flask_restplus import Api, Resource, abort, fields, ValidationError
from werkzeug.exceptions import HTTPException, NotFound, BadRequest
from project import parsers
from rq import Queue, Connection

from bvh_smooth.smooth_position import butterworth as pos_butterworth
from bvh_smooth.smooth_rotation import butterworth as rot_butterworth

# authentication
from flask_httpauth import HTTPBasicAuth

# initialization
from project.config import Config
from project.conversion_task import convert_openpose_baseline, convert_xnect
from project.parsers import user_metadata_parser

app = Flask(__name__)

app_settings = os.getenv("APP_SETTINGS")
app.config.from_object(app_settings)

# extensions
auth = HTTPBasicAuth()


blueprint = Blueprint('api', __name__, url_prefix='/api/v1', )
api = Api(blueprint, description="Motion Capturing from single RGB-Video", version="1", title="MoCap API")

app.register_blueprint(blueprint)

from rq import cancel_job
class ResultCode(enum.IntEnum):
    default = 2
    success = 1
    failure = -1
    pending = 0


class Count(Raw):
    def format(self, value):
        return len(value)


class BookmarkedByCurrentUser(Raw):
    def format(self, value):
        for v in value:
            if g.user.id == v.user_id:
                return True
        return False


stage_marshal = api.model('Stage', {
    'progress' : fields.Float(),
    'name': fields.String()
})

status_marshal = api.model('Status', {
    'finished': fields.Boolean,
    'stage': fields.Nested(stage_marshal),
    'problem': fields.Boolean
})

user_metadata_marshal = api.model('UserMetadata', {
    'prename': fields.String,
    'surname': fields.String,
    'website': fields.String,
    'email': fields.String
})
light_user_marshal = api.model('User', {
    'id': fields.String,
    'username': fields.String,
    'registration_date': fields.DateTime(dt_format='iso8601'),
})
user_marshal = api.model('User', {
    'id': fields.String,
    'username': fields.String,
    'registration_date': fields.DateTime(dt_format='iso8601'),
    'user_metadata': fields.Nested(user_metadata_marshal)
})
results_marshal = api.model('Result', {
    'id': fields.Integer,
    'max_people': fields.Integer,
    'result_code': fields.Integer(description="Result Code - Success: 1; Failure: 0; Pending: -1"),
    'date': fields.DateTime(dt_format='iso8601'),
    'output_video_url': fields.Url('api.results_result_output_video'),
    'output_bvh': fields.Url('api.results_result_bvh_file'),
    'render_url' : fields.Url('api.results_result_render_html')
})

tag_marshal = api.model('Tag', {
    'text': fields.String
})

bookmark_marshal = api.model('Bookmarks', {
    'category': fields.String,
    'user_id': fields.String,
    'job_id': fields.String,
    'count': Count(attribute="job.bookmarks")
})

delete_bookmark_marshal = api.model('Bookmarks', {
    'count': fields.Integer,
    'success': fields.Boolean
})


jobs_marshal = api.model('Job', {
    # TODO: Show user name
    'id': fields.String,
    'user': fields.Nested(light_user_marshal),
    'name': fields.String,
    'tags': fields.Nested(tag_marshal),
    'num_bookmarks': Count(attribute='bookmarks'),
    'bookmarked': BookmarkedByCurrentUser(attribute='bookmarks'),
    'public': fields.Boolean,
    'video_uploaded': fields.Boolean,
    'date_updated': fields.DateTime(dt_format='iso8601'),
    'upload_job_url': fields.Url('api.jobs_job_upload_video'),
    'input_video_url': fields.Url('api.jobs_job_source_video'),
    'thumbnail_url': fields.Url('api.jobs_job_thumbnail'),
    'result': fields.Nested(results_marshal),
})

# queue building
conn = redis.from_url(app.config["REDIS_URL"])

# import
import project.model.model as model

# redirect
@app.route("/")
def redirect_to_api():
    return redirect("/api/v1")

"""
Status
"""
status_space = api.namespace('status', description='Get the version status of the api', blueprint=blueprint)


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


def min_length(min_length):
    def validate(s):
        if len(s) >= min_length:
            return s
        raise ValidationError("Not long enough")
    return validate


user_parser = api.parser()
user_parser.add_argument('username', type=min_length(5), required=True, location='form')
user_parser.add_argument('password', type=min_length(5), required=True, location='form')

filter_parser = api.parser()
filter_parser.add_argument('border', type=int, location='args')
filter_parser.add_argument('u0', type=int, location='args')

# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@user_space.route("/", endpoint='with-parser')
class Users(Resource):
    @api.expect(user_parser)
    @api.response(409, 'A user with given username already exists')
    @api.response(200, 'User successfully created')
    @user_space.marshal_with(user_marshal)
    def post(self):
        args = user_parser.parse_args(strict=True)
        return model.add_user(args['username'], args['password'])

    @user_space.marshal_list_with(user_marshal)
    @api.response(200, 'Return users')
    def get(self):
        return model.get_users()


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
@user_space.route("/<int:id>")
class User(Resource):
    @api.response(404, 'The user with given id does not exist')
    @api.response(200, 'Return user with given id')
    @user_space.marshal_with(user_marshal)
    def get(self, id):
        return model.get_user(id)


@user_space.route("/<int:id>/metadata")
class UserMetadata(Resource):
    @api.expect(user_metadata_parser)
    @user_space.marshal_with(user_metadata_marshal)
    @auth.login_required
    def put(self, id):
        kwargs = user_metadata_parser.parse_args(strict=True)
        kwargs['user_id'] = g.user.id
        return model.update_metadata(**kwargs)


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
class Token(Resource):
    @auth.login_required
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return token which is valid for 5184000 seconds')
    def get(self):
        # duration in seconds
        duration = 5184000
        token = g.user.generate_auth_token(duration)
        print(g.user)
        return jsonify({'exp': time.time() + duration, 'token': token.decode('ascii'), 'duration': duration,
                        'user': g.user.serialize()})

"""
Jobs Space
"""
jobs_space = api.namespace('jobs', description='Manage Jobs of a user')


class JobDoesNotExist(HTTPException):
    code = 404
    description = "Job is pending"


def get_job_status(id):
    try:
        job = RedisJob.fetch(str(id), connection=conn)
    except NoSuchJobError as e:
        res = model.get_result_by_id(id)
        if res:
            if res.result_code == ResultCode.pending:
                return {"finished": False}
            else:
                return {"finished" : True}
        return {"message": "job not found"}, 404
    if job.is_finished:
        return {"finished": True}
    else:
        if job.is_failed:
            return {"finished": False, "problem": True}
        if 'stage' in job.meta:
            return {"stage": job.meta['stage'], "finished": False}
        return {"stage": {"name": "pending"}, "finished": False}


@jobs_space.route("/")
class Jobs(Resource):
    """
    Job status
    """

    @auth.login_required
    @jobs_space.marshal_list_with(jobs_marshal)
    @api.expect(parsers.get_jobs_parser)
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return all jobs belonging to the authorized user')
    def get(self):
        args = parsers.get_jobs_parser.parse_args()
        jobs = model.get_jobs_by_user_id(g.user.id, **args)
        return jobs

    @auth.login_required
    @api.expect(parsers.post_job_parser)
    @api.doc('get_something')
    @jobs_space.marshal_with(jobs_marshal)
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return the new job')
    def post(self):
        args = parsers.post_job_parser.parse_args()
        print(args)
        job = model.add_job(**{"user_id": g.user.id, "name": args['name'], "tags": args['tags']})
        # check if video is there
        # check if the sent file is actually a video.
        if args['video'] is not None and args['video'].mimetype == 'video/mp4':
            with Connection(conn):
                q = Queue()
                q.enqueue(convert_xnect, my_job_id=job.id, video=args['video'].read())
                job.video_uploaded = True
                model.db.session.commit()
                return job
        return job


@jobs_space.route("/bookmarks")
class Bookmarks(Resource):
    @auth.login_required
    @jobs_space.marshal_list_with(jobs_marshal)
    @api.expect(parsers.posts_parser)
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return all jobs belonging to the authorized user')
    def get(self):
        args = parsers.posts_parser.parse_args()
        return model.get_bookmarks_by_user(g.user.id, args['tags[]'])

@jobs_space.route("/bookmarks/<int:id>")
class Bookmark(Resource):
    @auth.login_required
    def post(self, id):
        return model.save_bookmark(id, g.user.id, None)

    @auth.login_required
    def delete(self, id):
        return model.remove_bookmark(id, g.user.id, None)



@jobs_space.route("/<int:id>/upload")
class JobUploadVideo(Resource):
    @auth.login_required
    @api.expect(parsers.upload_parser)
    @jobs_space.marshal_with(jobs_marshal)
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return the new job')
    @api.response(404, 'Job not found')
    def put(self, id):
        args = parsers.upload_parser.parse_args()
        # check if the sent file is actually a video.
        if not args['video'].mimetype == 'video/mp4':
            abort(415)
        job = model.get_job_by_id(id)
        if job is None:
            abort(404)
        elif job.video_uploaded is True:
            abort(409, "Video has been uploaded already")
        with Connection(conn):
            q = Queue()
            q.enqueue(convert_xnect, job_id=str(job.id), video=args['video'].read())
            job.video_uploaded = True
            model.db.session.commit()
            return job

@jobs_space.route("/failed")
class FailedJobs(Resource):
    @auth.login_required
    def delete(self):
        return model.delete_failed_jobs(g.user.id)

@jobs_space.route("/<int:id>")
@api.response(401, 'The user is not permitted to do this action')
class Job(Resource):
    # get via id
    @jobs_space.marshal_with(jobs_marshal)
    @auth.login_required
    @api.response(404, 'A job with the given id was not found')
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return the new job')
    def get(self, id):
        job = model.get_job_by_id(id)
        if job is None:
            abort(404, "The resource was not found.")
        return job

    @auth.login_required
    @api.response(404, 'A job with the given id was not found')
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return the new job')
    def delete(self, id):
        job = model.retrieve_job(id)
        if job.user_id != g.user.id:
            return 401
        if model.get_result_by_id(job.id).result_code == ResultCode.pending:
            return 400
        return model.delete_job(job.id)



@jobs_space.route("/<int:id>/status")
@api.response(401, 'The user is not permitted to do this action')
class JobStatus(Resource):
    """
    Job status
    """

    # get via id
    #@auth.login_required
    @jobs_space.marshal_with(status_marshal)
    @api.response(404, 'A job with the given id was not found')
    @api.response(401, 'The user is not permitted to do this action')
    @api.response(200, 'Return the new job')
    def get(self, id):
        # TODO: Authentication
        return get_job_status(id)



@jobs_space.route("/<int:id>/source_video")
class JobSourceVideo(Resource):
    #@auth.login_required
    @api.produces(["video/mp4"])
    @api.response(200, 'Return video file')
    @api.response(404, 'Not found')
    def get(self, id):
        # check if job exists
        job = model.get_job_by_id(id)
        directory = os.path.join(Config.CACHE_DIR, str(job.id))
        # check if result is succesful
        try:
            return send_from_directory(directory, Config.SOURCE_VIDEO_FILE,
                                       as_attachment=True, mimetype="video/mp4")
        except Exception as e:
            abort(404)


@jobs_space.route("/<int:id>/thumbnail")
class JobThumbnail(Resource):
    @auth.login_required
    @api.produces(["video/mp4"])
    @api.response(200, 'Return video file')
    def get(self, id):
        # check if job exists
        job = model.retrieve_job(id)
        directory = os.path.join(Config.CACHE_DIR, str(job.id))
        # check if result is succesful
        try:
            return send_from_directory(directory, Config.THUMBNAIL_FILE,
                                       as_attachment=True, mimetype="image/jpeg")
        except NotFound as e:
            abort(404)


@jobs_space.route("/statistics")
class JobStats(Resource):
    @auth.login_required
    @api.response(200, 'Return statistics about jobs')
    def get(self):
        return jsonify(model.get_job_stats(g.user.id))

class ResultFailedException(HTTPException):
    code = 404
    description = "Result has failed, hence there is no video"


def start_job(job_id, **kwargs):
    status = model.start_job(job_id, **kwargs)
    return status


"""
Results Space
"""

results_space = api.namespace('results', description='Results')


@results_space.route("/<int:id>")
class Result(Resource):
    @auth.login_required
    @results_space.marshal_with(results_marshal)
    @api.response(404, 'A result with the given id was not found')
    @api.response(200, 'Return the new job')
    @api.response(401, 'The user is not permitted to do this action')
    def get(self, id):
        return model.get_result_by_id(id)


@results_space.route("/")
class Results(Resource):
    @auth.login_required
    @results_space.marshal_list_with(results_marshal)
    @api.response(200, 'Return all the results that match to the given parameters')
    @api.response(401, 'The user is not permitted to do this action')
    def get(self):
        return model.filter_results(g.user.id)


@results_space.route("/<int:id>/output_video")
class ResultOutputVideo(Resource):
    @auth.login_required
    @api.produces(["video/mp4"])
    @api.response(200, 'Return video file')
    def get(self, id):
        # TODO: Generalize this function
        result = model.get_result_by_id(id)
        if result is None:
            return 404
        if result.result_code is not model.ResultCode.success:
            return 202
        path = os.path.join(Config.CACHE_DIR, str(result.id), Config.RESULT_DIR)
        return send_from_directory(path, Config.OUTPUT_VIDEO_FILE, as_attachment=True,
                                   attachment_filename=str(result.id) + ".mp4",
                                   mimetype="video/mp4")


def serve_zip(job, result):
    path = os.path.join(Config.CACHE_DIR, str(result.id), Config.RESULT_DIR)
    file_name = os.path.join(path, "bvhs.zip")
    if os.path.exists(file_name):
        return send_from_directory(path,
                                   "bvhs.zip",
                                   attachment_filename="%s by %s.zip" % (job.name, job.user.username),
                                   as_attachment=True,
                                   mimetype="application/zip")
    with zipfile.ZipFile(file_name, "w") as zf:
        for i in range(1, result.max_people + 1):
            name = "%s by %s (%d-%d).bvh" % (job.name, job.user.username, i, result.max_people)
            zf.write(os.path.join(path, Config.OUTPUT_BVH_FILE_RAW_NUMBERED % i), arcname=name)
    print("Zipped success...")
    return send_from_directory(path,
                               "bvhs.zip",
                               attachment_filename="%s by %s.zip" % (job.name, job.user.username),
                               as_attachment=True,
                               mimetype="application/zip")


@results_space.route("/<int:id>/bvh")
class ResultBvhFile(Resource):
    @auth.login_required
    @api.produces(["application/octet-stream"])
    @api.response(200, 'Return first bvh file')
    def get(self, id):
        result = model.get_result_by_id(id)
        job = model.get_job_by_id(id)
        if result is None:
            return 404
        if result.result_code is not model.ResultCode.success:
            return 202
        path = os.path.join(Config.CACHE_DIR, str(result.id), Config.RESULT_DIR)
        # return 1 person
        if result.max_people == 1:
            myfile = "%s by %s (%d-%d).bvh" % (job.name, job.user.username, 1, result.max_people)
            return send_from_directory(path, Config.OUTPUT_BVH_FILE_RAW_NUMBERED % 1, as_attachment=True,
                                               attachment_filename=myfile,
                                               mimetype="application/octet-stream")
        return serve_zip(job, result)




def filter_bvh(id, border, u0, nr):
    path = os.path.join(Config.CACHE_DIR, str(id), Config.RESULT_DIR)
    raw = os.path.join(path, Config.OUTPUT_BVH_FILE_RAW_NUMBERED % nr)
    output = os.path.join(path, Config.OUTPUT_BVH_FILE_FILTERED_DYNAMIC_NUMBERED % nr)
    rot_butterworth(raw, output, border, u0)
    #pos_butterworth(output, output, border, u0)


@results_space.route("/<int:id>/bvh/<int:person_id>")
class ResultBvhFileForPerson(Resource):
    @api.produces(["application/octet-stream"])
    @api.response(200, 'Return bvh file')
    @api.expect(filter_parser)
    def get(self, id, person_id):
        args = filter_parser.parse_args(strict=True)
        result = model.get_result_by_id(id)
        if result is None:
            return 404
        if result.result_code is not model.ResultCode.success:
            return 202
        if person_id > result.max_people or person_id < 1:
            raise BadRequest("Person %d does not exist - Max index is %d." % (person_id, result.max_people))
        path = os.path.join(Config.CACHE_DIR, str(result.id), Config.RESULT_DIR)
        job = model.get_job_by_id(id)
        myfile = "%s by %s (%d-%d).bvh" % (job.name, job.user.username, person_id, result.max_people)
        if args['border'] is not None and args['u0'] is not None:
            filter_bvh(result.id, args['border'], args['u0'], person_id)
            return send_from_directory(path, Config.OUTPUT_BVH_FILE_FILTERED_DYNAMIC_NUMBERED % person_id, as_attachment=True,
                                              attachment_filename=myfile,
                                              mimetype="application/octet-stream")
        return send_from_directory(path, Config.OUTPUT_BVH_FILE_RAW_NUMBERED % person_id, as_attachment=True,
                                   attachment_filename=myfile,
                                   mimetype="application/octet-stream")


@results_space.route("/<int:id>/render_html")
class ResultRenderHTML(Resource):
    @api.expect(parsers.render_parser)
    @api.expect(filter_parser)
    def get(self, id):
        args = filter_parser.parse_args(strict=True)
        headers = {'Content-Type' : 'text/html'}
        num_people = model.get_result_by_id(id).max_people
        urls = []
        if args['border'] is None or args['u0'] is None:
            for i in range(1, num_people + 1):
                urls.append(url_for('api.results_result_bvh_file_for_person', id=id, person_id=i))
        else:
            for i in range(1, num_people + 1):
                #ResultBvhFileForPersonFiltered
                urls.append(url_for('api.results_result_bvh_file_for_person', id=id, person_id=i,
                                    border=args['border'], u0=args['u0']))
                print(urls)
        return make_response(render_template('bvh_import/index.html',
                                             url_array=urls), 200, headers)
        #return redirect(url_for("api.results_result_render_html_for_person", id=id, person_id=1), 303)


@results_space.route("/<int:id>/render_html/<int:person_id>")
class ResultRenderHTMLForPerson(Resource):
    @api.expect(filter_parser)
    def get(self, id, person_id):
        headers = {'Content-Type' : 'text/html'}
        args = filter_parser.parse_args(strict=True)
        url = [url_for('api.results_result_bvh_file_for_person', id=id, person_id=person_id, border=args['border'], u0=args['u0'])]
        return make_response(render_template('bvh_import/index.html',
                                             url_array=url
                                             ), 200, headers)


@results_space.route("/<int:id>/render_html_filtered")
class ResultRenderHTMLFilteredDynamic(Resource):
    @api.expect(filter_parser)
    def get(self, id):
        args = filter_parser.parse_args(strict=True)
        headers = {'Content-Type' : 'text/html'}
        return make_response(render_template('bvh_import/index.html',
                                             current_url=url_for('api.results_result_bvh_file_filtered_dynamic', border=args['border'], u0 =args['u0'], id=id),
                                             original_url=url_for('api.results_result_bvh_file', id=id)),
                                                200, headers)


@results_space.route("/<int:id>/2d_data")
class Result2DData(Resource):
    def get(self, id):
        result = model.get_result_by_id(id)
        if result is None:
            return 404
        if result.result_code is not model.ResultCode.success:
            return 202
        path = os.path.join(Config.CACHE_DIR, str(result.id), 'results/imgs/2d_pose_vis')
        # create zip
        base_path = pathlib.Path(path)
        data = io.BytesIO()
        with zipfile.ZipFile(data, mode = 'w') as z:
            for f_name in base_path.iterdir():
                z.write(f_name)
        data.seek(0)
        return send_file(
            data,
            mimetype='application/zip',
            as_attachment=True,
            attachment_filename=str(result.id)+'.zip'
        )


"""
Posts space
"""

posts_space = api.namespace('posts', description='Posts feed')


# return all public posts
@posts_space.route("/")
class Posts(Resource):
    @api.response(200, 'Return the first 100 public posts')
    @api.expect(parsers.posts_parser)
    @auth.login_required
    @jobs_space.marshal_list_with(jobs_marshal)
    def get(self):
        args = parsers.posts_parser.parse_args(strict=True)
        if args['tags[]'] is None:
            return model.get_all_public_posts()
        return model.get_public_posts_filtered_by_tags(args['tags[]'])


@posts_space.route("/<int:id>")
class SinglePost(Resource):
    @auth.login_required
    @jobs_space.marshal_with(jobs_marshal)
    def post(self, id):
        return model.set_job_public(id, g.user.id)

    @auth.login_required
    @jobs_space.marshal_with(jobs_marshal)
    def delete(self, id):
        return model.set_job_private(id, g.user.id)


model.db.init_app(app)