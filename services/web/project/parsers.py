import uuid

import string
from flask_restplus import reqparse
import werkzeug

post_job_parser = reqparse.RequestParser()
post_job_parser.add_argument('name', default="My Project", type=str, location='form')
post_job_parser.add_argument('tags', type=str, location='form', action='append', default=[])
post_job_parser.add_argument('video', type=werkzeug.datastructures.FileStorage,
                             location='files', required=False, help='Video file in mp4 format')

get_jobs_parser = reqparse.RequestParser()
get_jobs_parser.add_argument('result_code', required=False, type=int, choices=[-1, 0, 1])

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('video',
                           type=werkzeug.datastructures.FileStorage,
                           location='files',
                           required=True,
                           help='Video File in mp4 format'
                           )

results_parser = reqparse.RequestParser()
results_parser.add_argument('result_code', type=int, help='Result Code: -1 = failed, 0 = pending, 1 = success')
results_parser.add_argument('result_type', type=int, help='Result Type: 0 = 2d, 1 = 3d')
results_parser.add_argument('job_id', help='Job id of the given result')
results_parser.add_argument('person_id', type=int, help='Result with person index')

job_start_parser = reqparse.RequestParser()
job_start_parser.add_argument('result_type', type=int, help='Result Type: 0 = 2d, 1 = 3d')
job_start_parser.add_argument('person_id', type=int, help='Result with person index')


user_metadata_parser = reqparse.RequestParser()
user_metadata_parser.add_argument('prename', type=str, required=False)
user_metadata_parser.add_argument('surname', type=str, required=False)
user_metadata_parser.add_argument('email', type=str, required=False)
user_metadata_parser.add_argument('website', type=str, required=False)

posts_parser = reqparse.RequestParser()
posts_parser.add_argument('tags[]', type=str, action='append')


render_parser = reqparse.RequestParser()
render_parser.add_argument('autorotate', type=bool, default=False)