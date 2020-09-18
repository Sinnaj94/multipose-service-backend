from rq.job import get_current_job

import progressbar
import cv2
import numpy as np
import os
from pathlib import Path
# from IPython.display import HTML
from matplotlib.animation import FuncAnimation

from video2bvh.pose_estimator_2d import openpose_estimator
from video2bvh.pose_estimator_3d import estimator_3d
from video2bvh.utils import smooth, vis, camera
from video2bvh.bvh_skeleton import h36m_skeleton, cmu_skeleton

from project.config import Config


def analyse_2d(cache_dir, persist=True):
    # get model
    e2d = openpose_estimator.OpenPoseEstimator(model_folder=Config.OPENPOSE_MODELS_PATH)

    cap = cv2.VideoCapture(str(cache_dir / Config.SOURCE_VIDEO_FILE))
    video_length = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    keypoints_list = []
    img_width, img_height = None, None
    # progess bar visualizes
    bar = progressbar.ProgressBar(maxval=video_length,
                                  widgets=[progressbar.Bar('=', '[', ']'), ' ', progressbar.Percentage()])
    i = 0
    bar.start()
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            # analyse frame
        img_height = frame.shape[0]
        img_width = frame.shape[1]
        # all keypoints
        all_keypoints = e2d.estimate(img_list=[frame])

        keypoints = all_keypoints[0]
        if not isinstance(keypoints, np.ndarray) or len(keypoints.shape) != 3:
            keypoints_list.append(None)
        else:
            # todo: What to do if keypoints list has multiple persons?
            keypoints_list.append(keypoints[0])
        i += 1
        bar.update(i)
    cap.release()
    config = {'img_width': img_width, 'img_height': img_height, 'frames': video_length, 'fps': fps}

    return keypoints_list, config


def analyse_3d(pose2d, conf, cache_dir):
    e3d = estimator_3d.Estimator3D(
        config_file=os.path.join(Config.MODELS_3D_DIR, "video_pose.yaml"),
        checkpoint_file=os.path.join(Config.MODELS_3D_DIR, 'best_58.58.pth')
    )
    pose3d = e3d.estimate(pose2d, image_width=conf['img_width'], image_height=conf['img_height'])
    subject = 'S1'
    cam_id = '55011271'
    cam_params = camera.load_camera_params('./cameras.h5')[subject][cam_id]
    R = cam_params['R']
    T = 0
    azimuth = cam_params['azimuth']

    # save config
    conf = {'subject': subject,
            'cam_id': cam_id,
            'cam_params': cam_params,
            'R': R,
            'T': T,
            'azimuth': azimuth}

    pose3d_world = camera.camera2world(pose=pose3d, R=R, T=T)
    pose3d_world[:, :, 2] -= np.min(pose3d_world[:, :, 2])  #
    return pose3d_world, conf


def export_video(pose3d_world, video_file, config, fps=60):
    # TODO: Machen
    h36m_skel = h36m_skeleton.H36mSkeleton()
    ani = vis.vis_3d_keypoints_sequence(
        keypoints_sequence=pose3d_world,
        skeleton=h36m_skel,
        azimuth=np.array(config['azimuth']),
        fps=fps,
        output_file=video_file
    )



def convert(video, user_id):
    from project.model import model
    job_name = str(get_current_job().get_id())
    # add to database
    model.add_job(**{"job_id": job_name,
                     "user_id": user_id})
    # The cache dir will look like that : cache/aabb-ccc-dddd-fff-ggg/ (UUID)
    cache_dir = Path(os.path.join(Config.CACHE_DIR, job_name))

    # Create a directory where the cache is stored.
    if not cache_dir.exists():
        os.makedirs(cache_dir)

    # save the video in the cache folder
    filename = os.path.join(cache_dir, Config.SOURCE_VIDEO_FILE)
    with(open(filename, 'wb')) as file:
        file.write(video)
    file.close()

    pose2d_file = cache_dir / Config.DATA_2D_FILE
    pose3d_file = cache_dir / Config.DATA_3D_FILE
    pose3d_world = None
    points_list = None
    if not pose2d_file.exists() or not Config.CACHE_RESULTS:
        print("Beginning to 2d analyse job %s" % job_name)

        points_list, config_2d = analyse_2d(cache_dir)

        points_list = smooth.filter_missing_value(
            keypoints_list=points_list,
            method='ignore'
        )
        if not points_list:
            kwargs = {"job_id": job_name,
                      "user_id": user_id,
                      "result_code": model.ResultCode.failure,
                      "file_directory": str(cache_dir.absolute())}

            model.save_result(**kwargs)
            return None
        pose2d = np.stack(points_list)[:, :, :2]
        print("Finished to 2d analyse job %s" % job_name)

        if Config.CACHE_RESULTS:
            np.save(cache_dir / '2d_pose.npy', pose2d)
            np.save(cache_dir / '2d_config.npy', config_2d)
    else:
        print("Found 2d Cache for %s" % job_name)
        pose2d = np.load(pose2d_file).values()
        config_2d = np.load(cache_dir / '2d_config.npy').values()

    # estimate 3d pose
    #
    if not pose3d_file.exists() or not Config.CACHE_RESULTS:
        print("Beginning to 3d analyse job %s" % job_name)
        pose3d_world, conf_3d = analyse_3d(pose2d, config_2d, cache_dir)
        print("Finished to 3d analyse job %s" % job_name)
        if Config.CACHE_RESULTS:
            np.save(cache_dir / '3d_pose.npy', pose3d_world)
            np.save(cache_dir / '3d_conf.npy', conf_3d)
    else:
        print("Found 3d Cache for %s" % job_name)
        pose3d_world = np.load(cache_dir / '3d_pose.npy').values()
        conf_3d = np.load(cache_dir / '3d_conf.npy').values()

    # GIF
    print("Generating a preview Video for %s" % job_name)
    export_video(pose3d_world, cache_dir / Config.OUTPUT_VIDEO_FILE, conf_3d, fps=config_2d['fps'])

    print("Generating a BVH file for %s" % job_name)
    bvh_file = cache_dir / f'{job_name}.bvh'
    if Config.EXPORT_FORMAT == "CMU":
        cmu_skel = cmu_skeleton.CMUSkeleton()
        channels, header = cmu_skel.poses2bvh(pose3d_world, output_file=bvh_file)
    elif Config.EXPORT_FORMAT == "H36M":
        h36m_skel = h36m_skeleton.H36mSkeleton()
        _ = h36m_skel.poses2bvh(pose3d_world, output_file=bvh_file)
    else:
        raise ValueError("Unrecognized Panoptic style %s. You must decide between CMU and H36M.", Config.EXPORT_FORMAT)

    kwargs = {"job_id": job_name,
              "user_id": user_id,
              "result_code": model.ResultCode.success,
              "file_directory": str(cache_dir.absolute())}

    model.save_result(**kwargs)
    return True
