import uuid

import string
from flask_restplus import reqparse
import werkzeug

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('mp4_file',
                           type=werkzeug.datastructures.FileStorage,
                           location='files',
                           required=True,
                           help='mp4 File'
                           )
upload_parser.add_argument('autostart', type=bool, help="Automatically start the job", default=True)

results_parser = reqparse.RequestParser()
results_parser.add_argument('result_code', type=int, help='Result Code: -1 = failed, 0 = pending, 1 = success')
results_parser.add_argument('result_type', type=int, help='Result Type: 0 = 2d, 1 = 3d')
results_parser.add_argument('job_id', help='Job id of the given result')
results_parser.add_argument('person_id', type=int, help='Result with person index')
