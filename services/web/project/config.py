import os


basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite://")
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    VIDEO_DIR = "./data/jobs"
    CACHE_DIR = "/usr/data"
    RESULT_DIR = "results"
    MODELS_3D_DIR = "./3d_models"
    OPENPOSE_MODELS_PATH = "/openpose/models"
    REDIS_URL = "redis://redis:6379/0"
    QUEUES = ["default"]
    # Configure, if results are stored in files or not
    CACHE_RESULTS = True
    # POSSIBILITIES: CMU / H36M
    EXPORT_FORMAT = "CMU"
    SOURCE_VIDEO_FILE = "source_video.mp4"
    OUTPUT_VIDEO_FILE = "output_video.mp4"
    OUTPUT_BVH_FILE = "output_bvh.bvh"
    DATA_2D_FILE = "data_2d.npy"
    CONFIG_2D_FILE = "config_2d.npy"
    DATA_3D_FILE = "data_3d.npy"


