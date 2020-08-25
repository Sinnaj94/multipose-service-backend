from flask_restplus import reqparse
import werkzeug

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('mp4_file',
                           type=werkzeug.datastructures.FileStorage,
                           location='files',
                           required=True,
                           help='mp4 File'
                           )

parser = reqparse.RequestParser()
