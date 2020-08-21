#!flask/bin/python
from flask import Flask
from flask_restplus import Api, Resource, fields

flask_app = Flask(__name__)
app = Api(app=flask_app,
          version="1.0",
          title="Motion Capturing API",
          description="Motion Capturing Library from single RGB Videos")

name_space = app.namespace('2d-analysis', description='2D Analysis')


# todo: content type set to video
analysis_model_2d = app.model('2D Analysis Model',
                              {
                                  'video': fields.Raw(required=True,
                                                      description="RGB Video Input File",
                                                      help="Video to be analysed should be sent.",
                                                      type="video/mp4")
                              })


@name_space.route("/")
class Analysis2DClass(Resource):
    def get(self):
        return {
            "status": "Got new data"
        }

    @app.expect(analysis_model_2d)
    def post(self):
        return {
            "status": "Posted the video"
        }


if __name__ == '__main__':
    flask_app.run(debug=True)
