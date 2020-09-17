import os


basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite://")
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    VIDEO_DIR = "./data/jobs"
    CACHE_DIR = "./cache"
    MODELS_3D_DIR = "./3d_models"
    OPENPOSE_MODELS_PATH = "/openpose/models"
    REDIS_URL = "redis://redis:6379/0"
    QUEUES = ["default"]
    CACHE_RESULTS = True
    # POSSIBILITIES: CMU / H36M
    EXPORT_FORMAT = "CMU"