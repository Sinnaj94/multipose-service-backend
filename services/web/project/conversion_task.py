import math
import os
import time
from pathlib import Path

import requests
from bvh_smooth.smooth_position import butterworth as pos_butterworth
from bvh_smooth.smooth_rotation import butterworth as rot_butterworth
from bvh_smooth.smooth_position import average as pos_avrg
from bvh_smooth.smooth_rotation import average as rot_avrg

import cv2
import skvideo.io
from flask import request
from rq.job import get_current_job
from video2bvh.bvh_skeleton import h36m_skeleton, cmu_skeleton, openpose_skeleton
from video2bvh.pose_estimator_3d import estimator_3d
from video2bvh.utils import smooth, vis, camera

from project.config import Config
import numpy as np
from video2bvh.bvh_skeleton import muco_3dhp_skeleton


# from IPython.display import HTML


def analyse_2d(job_cache_dir, thumbnail_path, persist=True):
    from video2bvh.pose_estimator_2d import openpose_estimator
    # get model
    e2d = openpose_estimator.OpenPoseEstimator(model_folder=Config.OPENPOSE_MODELS_PATH)
    videogen = skvideo.io.FFmpegReader(str(job_cache_dir / Config.SOURCE_VIDEO_FILE))
    keypoints_list = []

    (video_length, img_height, img_width, _) = videogen.getShape()
    i = 0
    job = get_current_job()

    thumbnail = None
    for frame in videogen.nextFrame():
        all_keypoints = e2d.estimate(img_list=[frame])

        keypoints = all_keypoints[0]
        if not isinstance(keypoints, np.ndarray) or len(keypoints.shape) != 3:
            keypoints_list.append(None)
        else:
            # todo: What to do if keypoints list has multiple persons?
            keypoints_list.append(keypoints[0])
        i += 1
        # save progress
        job.meta['stage']['progress'] = round(i / video_length, 2)
        job.save_meta()

    videogen.close()
    # todo: GET FPS FROM META
    config = {'img_width': img_width, 'img_height': img_height, 'frames': video_length, 'fps': 60}

    return keypoints_list, config, thumbnail


def analyse_3d(pose2d, conf, result_cache_dir):
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
    h36m_skel = h36m_skeleton.H36mSkeleton()
    ani = vis.vis_3d_keypoints_sequence(
        keypoints_sequence=pose3d_world,
        skeleton=h36m_skel,
        azimuth=np.array(config['azimuth']),
        fps=fps,
        output_file=video_file
    )


def scale_world_3d(pose3d_world, scale_factor=.1):
    return pose3d_world * scale_factor


def get_rotation_matrix(axis, theta):
    # Source: https://stackoverflow.com/questions/6802577/rotation-of-3d-vector/25709323
    # Euler Rodrigues Formula
    axis = np.asarray(axis)
    axis = axis / math.sqrt(np.dot(axis, axis))
    a = math.cos(theta / 2.0)
    b, c, d = -axis * math.sin(theta / 2.0)
    aa, bb, cc, dd = a * a, b * b, c * c, d * d
    bc, ad, ac, ab, bd, cd = b * c, a * d, a * c, a * b, b * d, c * d
    return np.array([[aa + bb - cc - dd, 2 * (bc + ad), 2 * (bd - ac)],
                     [2 * (bc - ad), aa + cc - bb - dd, 2 * (cd + ab)],
                     [2 * (bd + ac), 2 * (cd - ab), aa + dd - bb - cc]])


def rotate_world_3d(pose3d_world, axis, radians):
    return np.array([[np.dot(get_rotation_matrix(axis, radians), bone) for bone in frame] for frame in pose3d_world])


def export_video_2d(keypoints_list, video_file, output_dir):
    cap = cv2.VideoCapture(str(video_file))
    vis_result_dir = output_dir / '2d_pose_vis'  # path to save the visualized images
    if not vis_result_dir.exists():
        os.makedirs(vis_result_dir)

    op_skel = openpose_skeleton.OpenPoseSkeleton()

    for i, keypoints in enumerate(keypoints_list):
        ret, frame = cap.read()
        if not ret:
            break

        # keypoint whose detect confidence under kp_thresh will not be visualized
        vis.vis_2d_keypoints(
            keypoints=keypoints,
            img=frame,
            skeleton=op_skel,
            kp_thresh=0.4,
            output_file=vis_result_dir / f'{i:04d}.png'
        )
    cap.release()


def prepare(video):
    from project.model import model
    job = get_current_job()

    job.meta['stage'] = {'name': 'preparing', 'progress': None}

    job_id = str(get_current_job().get_id())
    # add to database
    job_cache_dir = Path(os.path.join(Config.CACHE_DIR, job_id))

    # The cache dir will look like that : cache/aabb-ccc-dddd-fff-ggg/ (UUID)
    # Create a directory where the cache is stored.
    if not job_cache_dir.exists():
        os.makedirs(job_cache_dir)

    # save the SOURCE video in the cache folder
    filename = os.path.join(job_cache_dir, Config.SOURCE_VIDEO_FILE)
    print("Saving video at %s" % filename)
    with(open(filename, 'wb')) as file:
        file.write(video)
    file.close()

    # save thumbnail
    videogen = skvideo.io.FFmpegReader(filename)
    for frame in videogen.nextFrame():
        thumbnail_path = job_cache_dir / Config.THUMBNAIL_FILE
        skvideo.io.vwrite(str(thumbnail_path), frame)
        videogen.close()
        break

    fps = videogen.inputfps

    # result
    result = model.get_result_by_id(get_current_job().get_id())
    result.result_code = model.ResultCode.pending
    model.db.session.commit()

    result_cache_dir = Path(os.path.join(job_cache_dir, Config.RESULT_DIR))

    if not result_cache_dir.exists():
        os.makedirs(result_cache_dir)

    pose2d_file = result_cache_dir / Config.DATA_2D_FILE
    pose3d_file = result_cache_dir / Config.DATA_3D_FILE
    # create a thumbnail
    job.meta['stage'] = {'name': 'thumbnail'}
    job.save_meta()

    pose3d_world = None
    points_list = None
    job.meta['stage'] = {'name': '2d', 'progress': 0}
    job.save_meta()

    return job, job_id, model, job_cache_dir, pose2d_file, pose3d_file, thumbnail_path, filename, result, \
           result_cache_dir, fps


def convert_openpose_baseline(video):
    job, job_id, model, job_cache_dir, pose2d_file, pose3d_file, thumbnail_path, filename, result, result_cache_dir, \
    fps = prepare(video)

    if not pose2d_file.exists() or not Config.CACHE_RESULTS:
        print("Beginning to 2d analyse job %s" % job_id)

        points_list, config_2d, thumbnail = analyse_2d(job_cache_dir, thumbnail_path)

        points_list = smooth.filter_missing_value(
            keypoints_list=points_list,
            method='ignore'
        )

        if not points_list:
            print("Job analysis failed.")
            result.result_code = model.ResultCode.failure
            model.db.session.commit()
            return False
        pose2d = np.stack(points_list)[:, :, :2]
        print("Finished to 2d analyse job %s" % job_id)
        print("---")
        print("2D Rendering the video")
        job.meta['stage'] = {'name': '2d render', 'progress': None}
        export_video_2d(points_list, filename, result_cache_dir / "imgs")
        print("2D Rendering finished")
        if Config.CACHE_RESULTS:
            np.save(result_cache_dir / '2d_pose.npy', pose2d)
            np.save(result_cache_dir / '2d_config.npy', config_2d)

    else:
        print("Found 2d Cache for %s" % job_id)
        pose2d = np.load(pose2d_file).values()
        config_2d = np.load(result_cache_dir / '2d_config.npy').values()

    job.meta['stage'] = {'name': '3d'}
    job.save_meta()

    if not pose3d_file.exists() or not Config.CACHE_RESULTS:
        print("Beginning to 3d analyse job %s" % job_id)
        pose3d_world, conf_3d = analyse_3d(pose2d, config_2d, result_cache_dir)
        print("Finished to 3d analyse job %s" % job_id)
        if Config.CACHE_RESULTS:
            np.save(result_cache_dir / '3d_pose.npy', pose3d_world)
            np.save(result_cache_dir / '3d_conf.npy', conf_3d)
    else:
        print("Found 3d Cache for %s" % job_id)
        pose3d_world = np.load(result_cache_dir / '3d_pose.npy').values()
        conf_3d = np.load(result_cache_dir / '3d_conf.npy').values()

    # GIF
    job.meta['stage'] = {'name': 'render'}

    job.save_meta()
    print("Generating a preview Video for %s" % job_id)
    export_video(pose3d_world, result_cache_dir / Config.OUTPUT_VIDEO_FILE, conf_3d, fps=config_2d['fps'])

    job.meta['stage'] = {'name': 'bvh'}
    job.save_meta()

    print("Generating a BVH file for %s" % job_id)
    bvh_file = result_cache_dir / Config.OUTPUT_BVH_FILE
    pose3d_world = scale_world_3d(pose3d_world)
    pose3d_world = rotate_world_3d(pose3d_world, [-1, 0, 0], math.pi * 90 / 180)
    if Config.EXPORT_FORMAT == "CMU":
        cmu_skel = cmu_skeleton.CMUSkeleton()
        channels, header = cmu_skel.poses2bvh(pose3d_world, output_file=bvh_file)
    elif Config.EXPORT_FORMAT == "H36M":
        h36m_skel = h36m_skeleton.H36mSkeleton()
        _ = h36m_skel.poses2bvh(pose3d_world, output_file=bvh_file)
    else:
        raise ValueError("Unrecognized Panoptic style %s. You must decide between CMU and H36M.", Config.EXPORT_FORMAT)

    result.result_code = model.ResultCode.success
    model.db.session.commit()
    return True


def analyse_xnect(video, job_id, result_cache_dir, result, model):
    # Make request to xnect server
    try:
        files = {"video": ("video.mp4", video, "video/mp4")}
        r = requests.post("http://xnect:8081/%s" % str(job_id), files=files, timeout=999999)
        if r.status_code != 200:
            result.result_code = model.ResultCode.failure
            model.db.session.commit()
            return False
        finished = False
        while not finished:
            r = requests.get("http://xnect:8081/finished")
            finished = r.json()['finished']
            print("Not yet finished...")
            time.sleep(1)

        urls = ["raw2d", "raw3d", "ik3d"]
        paths = {}
        for url in urls:
            r = requests.get("http://xnect:8081/%s/%s" % (str(job_id), url))
            path = os.path.join(result_cache_dir, "%s.txt" % url)
            open(path, 'wb').write(r.content)
            if os.path.getsize(path) <= 1:
                result.result_code = model.ResultCode.failure
                model.db.session.commit()
                return False
            paths[url] = path
        return paths
    except:
        result.result_code = model.ResultCode.failure
        model.db.session.commit()
        return False


def interpolate_poses(pred, start, end):
    start_data = pred[start]["ik3d"][0] * 0.01
    end_data = pred[end]["ik3d"][0] * 0.01
    print("Found one", start_data)


def convert_xnect(video):
    job, job_id, model, job_cache_dir, pose2d_file, pose3d_file, thumbnail_path, filename, result, result_cache_dir,\
    fps = prepare(video)
    job.meta['stage'] = {'name': 'xnect', 'progress': None}

    paths = analyse_xnect(video, job_id, result_cache_dir, result, model)
    if paths is False:
        return False
    raw2d, raw3d, ik3d = paths["raw2d"], paths["raw3d"], paths["ik3d"]
    pred, first_complete, num_people = xnect_to_bvh(raw2d, raw3d, ik3d, result, model)

    keypoints = []
    last_cached_index = -1
    for pidx in range(num_people):
        person_keypoints = []
        for idx in range(first_complete, len(pred)):
            # TODO: Interpolate more
            if pred[idx]['valid_ik'][pidx] and not pred[idx]['is_outlier'][pidx]:
                person_keypoints.append(pred[idx]["ik3d"][pidx] * 0.01)
                last_cached_index = idx
            else:
                if last_cached_index > -1:
                    person_keypoints.append(pred[last_cached_index]["ik3d"][pidx] * 0.01)
        keypoints.append(person_keypoints)

    # interpolation via scipy
    for i in range(len(keypoints)):
        print("Saving bvh nr.", i)
        skel = muco_3dhp_skeleton.Muco3DHPSkeleton()
        raw = result_cache_dir / (Config.OUTPUT_BVH_FILE_RAW_NUMBERED % (i + 1))
        # raw file
        channels, header = skel.poses2bvh(np.array(keypoints[i]), output_file=raw, frame_rate=fps)

    result.result_code = model.ResultCode.success
    result.max_people = num_people
    model.db.session.commit()
    return True


def euc_dist(a, b):
    s = len(a)
    summe = 0
    for i in range(s):
        summe += pow((a[i] - b[i]), 2)
    return math.sqrt(summe)


def calc_distance(a, b):
    erg = 0
    s = len(a)
    for i in range(s):
        erg += euc_dist(a[i], b[i])
    return erg


def find_first_complete_keyframe(pred, num_people):
    for idx in range(0, len(pred)):
        valid = 0
        for pidx in range(len(pred[idx]["valid_ik"])):
            if pred[idx]["valid_ik"][pidx]:
                valid += 1
                if valid == num_people:
                    return idx


def sort(start, end, pred, backwards=False):
    step = 1
    if backwards:
        step = -1
    for idx in range(start, end, step):
        current_data = np.empty_like(pred[idx]["ik3d"])
        current_valid = np.empty_like(pred[idx]["valid_ik"])
        for pidx in range(len(pred[idx]["ik3d"])):
            if pred[idx]["valid_ik"][pidx]:
                if backwards:
                    deltaidx = idx + 1
                else:
                    deltaidx = idx - 1
                best_match = -1
                distance = float('inf')
                a = 0
                for i, val in enumerate(pred[deltaidx]["ik3d"]):
                    cur_dist = calc_distance(pred[idx]["ik3d"][pidx], val)
                    if cur_dist < distance:
                        distance = cur_dist
                        best_match = i
                current_data[best_match] = pred[idx]["ik3d"][pidx]
                current_valid[best_match] = pred[idx]["valid_ik"][pidx]
            else:
                pass
        pred[idx]["ik3d"] = current_data
        pred[idx]["valid_ik"] = current_valid


def outlier_map(pred, num_people, m):
    for pidx in range(0, num_people):
        dists = np.zeros(len(pred))
        for idx in range(len(pred)):
            dists[idx] = calc_distance(pred[idx]["ik3d"][pidx], pred[idx - 1]["ik3d"][pidx])
        mean = np.mean(dists)
        outlier_map = [(dist > mean * m) for dist in dists]
        for i in range(len(outlier_map)):
            pred[i]["is_outlier"][pidx] = outlier_map[i]


def readjust_person_index_ik3d(pred, max_people):
    first_complete = find_first_complete_keyframe(pred, max_people)
    print("First complete", first_complete)
    print("Forward sort")
    sort(1, len(pred), pred, False)
    print("Backwards sort")
    sort(len(pred) - 2, 0, pred, True)
    outlier_map(pred, max_people, 3)
    return first_complete


def xnect_to_bvh(raw2d_file, raw3d_file, ik3d_file, result, model):
    p2d = np.loadtxt(raw2d_file)
    p3d = np.loadtxt(raw3d_file)
    i3d = np.loadtxt(ik3d_file)
    if len(i3d) == 0:
        result.result_code = model.ResultCode.failure
        return False
    num_people = int(np.max(p2d.T[1]) + 1)
    print(num_people)
    size = i3d.shape[0]
    pred = []
    pred_len = int(max(np.max(i3d.T[0]), np.max(p3d.T[0]))) + 1
    for i in range(pred_len):
        # set dictionary
        pred.append({
            "pred2d": np.zeros([num_people, 14, 2]),
            "pred3d": np.zeros([num_people, 21, 3]),
            "ik3d": np.zeros([num_people, 21, 3]),
            "adjusted_ik3d": np.zeros([num_people, 21, 3]),
            "vis": np.zeros([num_people, 14, 1]),
            "valid_raw": np.zeros([num_people], dtype=bool),
            "valid_ik": np.zeros([num_people], dtype=bool),
            "is_outlier": np.zeros([num_people], dtype=bool)
        })

    # iterate through keyframes of p3d
    origin = None
    for i in range(p3d.shape[0]):
        idx = int(p2d[i][0])
        pidx = int(p2d[i][1])
        pred[idx]["pred2d"][pidx] = np.reshape(p2d[i][2:], [14, 2])
        tmp = np.reshape(p3d[i][2:], [21, 3])
        if origin is None:
            direction_vector = tmp[13] - tmp[10]
            origin = tmp[13] - direction_vector * .5
        pred[idx]["pred3d"][pidx] = tmp - origin
        pred[idx]["valid_raw"][pidx] = True
        pred[idx]["vis"][pidx] = (np.greater(pred[idx]["pred2d"][pidx].T[0], 0) &
                                  np.greater(pred[idx]["pred2d"][pidx].T[1], 0)).reshape([14, 1])

    origin = None
    for i in range(i3d.shape[0]):
        idx = int(i3d[i][0])
        pidx = int(i3d[i][1])
        tmp = np.reshape(i3d[i][2:], [21, 3])
        if origin is None:
            direction_vector = tmp[13] - tmp[10]
            origin = tmp[13] - direction_vector * .5
        pred[idx]["ik3d"][pidx] = tmp - origin
        pred[idx]["valid_ik"][pidx] = True
    print("Readjusting person index ik3d")
    first_complete = readjust_person_index_ik3d(pred, num_people)
    return pred, first_complete, num_people
