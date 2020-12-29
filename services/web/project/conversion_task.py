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


def prepare(my_job_id, video):
    """
    prepare a job and return several parameters
    :param my_job_id: database id of the job
    :param video: video file as bytes array
    """
    from project.model import model
    # get the current job
    job = get_current_job()

    job.meta['stage'] = {'name': 'preparing', 'progress': None}

    # get the redis id for the job
    job_id = str(get_current_job().get_id())
    # add to database
    job_cache_dir = Path(os.path.join(Config.CACHE_DIR, str(my_job_id)))

    # The cache dir will look like that : cache/aabb-ccc-dddd-fff-ggg/ (UUID)
    # Create a directory where the cache is stored.
    if not job_cache_dir.exists():
        os.makedirs(job_cache_dir)

    # save the source video in the cache folder
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

    # retrieve the fps from the video
    fps = videogen.inputfps

    # result
    result = model.get_result_by_id(my_job_id)
    result.result_code = model.ResultCode.pending
    model.db.session.commit()

    result_cache_dir = Path(os.path.join(job_cache_dir, Config.RESULT_DIR))

    if not result_cache_dir.exists():
        os.makedirs(result_cache_dir)

    # get specific file locations
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


def analyse_xnect(video, job_id, result_cache_dir, result, model):
    """
    analyse a video file in xnect container
    :param video: video as byte data
    :param job_id: redis job id
    :param result_cache_dir: cache dir of the current job
    :param result: current result from model
    :param model: model reference to database
    :return: paths to raw xnect data, or false, if failed
    """
    try:
        # send the video to xnect via http post request
        files = {"video": ("video.mp4", video, "video/mp4")}
        r = requests.post("http://xnect:8081/%s" % str(job_id), files=files, timeout=999999)
        if r.status_code != 200:
            result.result_code = model.ResultCode.failure
            model.db.session.commit()
            return False
        finished = False
        # check via get request, if the job has finished yet
        while not finished:
            r = requests.get("http://xnect:8081/finished")
            finished = r.json()['finished']
            print("Not yet finished...")
            time.sleep(1)
        # get the data for following urls:
        urls = ["raw2d", "raw3d", "ik3d"]
        paths = {}
        for url in urls:
            # save data for the urls
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
        # set failure, if an error occurs
        result.result_code = model.ResultCode.failure
        model.db.session.commit()
        return False


def interpolate_poses(pred, start, end):
    """
    Interpolate poses between a start and an end frame
    :param pred: Poses array
    :param start: Start frame
    :param end: End frame
    :return:
    """
    start_data = pred[start]["ik3d"][0] * 0.01
    end_data = pred[end]["ik3d"][0] * 0.01
    print("Found one", start_data)


def convert_xnect(my_job_id, video):
    """
    Sends a video with a given redis id to xnect
    :param my_job_id: redis id
    :param video: video as bytecode
    :return:
    """
    # prepare the video
    job, job_id, model, job_cache_dir, pose2d_file, pose3d_file, thumbnail_path, filename, result, result_cache_dir, \
    fps = prepare(my_job_id, video)
    # set the progress to indeterminate
    job.meta['stage'] = {'name': 'xnect', 'progress': None}
    # analyse the actual video
    paths = analyse_xnect(video, str(my_job_id), result_cache_dir, result, model)
    if paths is False:
        # there is no data, so return
        result.result_code = model.ResultCode.failure
        return False

    # convert the data
    raw2d, raw3d, ik3d = paths["raw2d"], paths["raw3d"], paths["ik3d"]
    pred, first_complete, num_people = xnect_to_bvh(raw2d, raw3d, ik3d, result, model)

    keypoints = []
    last_cached_index = -1
    for pidx in range(num_people):
        person_keypoints = []
        for idx in range(first_complete, len(pred)):
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
    """
    euclidian distance between a and b
    :param a: array of point a
    :param b: array of point b
    :return: euc distance
    """
    s = len(a)
    summe = 0
    for i in range(s):
        summe += pow((a[i] - b[i]), 2)
    return math.sqrt(summe)


def calc_distance(a, b):
    """
    sum of euclidian distance of two multidimensional arrays
    :param a: multidimensional array
    :param b: multidimensional array
    :return: sum of euclidian distance of multi array
    """
    erg = 0
    s = len(a)
    for i in range(s):
        erg += euc_dist(a[i], b[i])
    return erg


def find_first_complete_keyframe(pred, num_people):
    """
    find the first complete keyframe in an xnect predictions array
    :param pred: xnect predictions array
    :param num_people: number of people
    :return: first frame as index
    """
    for idx in range(0, len(pred)):
        valid = 0
        for pidx in range(len(pred[idx]["valid_ik"])):
            if pred[idx]["valid_ik"][pidx]:
                valid += 1
                if valid == num_people:
                    return idx


def sort(start, end, pred, backwards=False):
    """
    sorting algorithm to reindex the people
    :param start: first frame
    :param end: last frame
    :param pred: preconverted prediction xnect array
    :param backwards: if the array should be sorted backwards instead of forward
    :return: sorted array with correct person indices
    """
    step = 1
    if backwards:
        step = -1
    # go through prediction array from start to end frame
    for idx in range(start, end, step):
        # get the current data and check if the keyframe is valid
        current_data = np.empty_like(pred[idx]["ik3d"])
        current_valid = np.empty_like(pred[idx]["valid_ik"])
        # go through each keyframe and check the best match for each person using the keyframe before
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
    """
    get all outliers as a map
    """
    # go through each keyframe and check if the keyframe is an outlier
    for pidx in range(0, num_people):
        dists = np.zeros(len(pred))
        for idx in range(len(pred)):
            dists[idx] = calc_distance(pred[idx]["ik3d"][pidx], pred[idx - 1]["ik3d"][pidx])
        mean = np.mean(dists)
        # it is an outlier, if the distance to a person is m times the distance of the mean distance of this person
        outlier_map = [(dist > mean * m) for dist in dists]
        for i in range(len(outlier_map)):
            pred[i]["is_outlier"][pidx] = outlier_map[i]


def readjust_person_index_ik3d(pred, max_people):
    """
    readjust all person index, including forward and backwards sort and outlier map
    :param pred: sorted prediction array
    :param max_people: number of tracked people
    :return: adjusted array with correct person indizes
    """
    first_complete = find_first_complete_keyframe(pred, max_people)
    print("First complete", first_complete)
    print("Forward sort")
    sort(1, len(pred), pred, False)
    print("Backwards sort")
    sort(len(pred) - 2, 0, pred, True)
    outlier_map(pred, max_people, 3)
    return first_complete


def xnect_to_bvh(raw2d_file, raw3d_file, ik3d_file, result, model):
    """
    converts the xnect data to a bvh file
    :param raw2d_file: raw 2d data from xnect
    :param raw3d_file: raw 3d data from xnect
    :param ik3d_file: raw 3d data (ik) from xnect
    :param result: result object from model
    :param model: model to the database
    :return: sorted array, first complete keyframe and number of people
    """
    # load the files as a numpy array
    p2d = np.loadtxt(raw2d_file)
    p3d = np.loadtxt(raw3d_file)
    i3d = np.loadtxt(ik3d_file)
    # if there is no data, abort the execution and set the result to failed
    if len(i3d) == 0:
        result.result_code = model.ResultCode.failure
        model.db.session.commit()
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
    # source: XNECT Matlab demo import
    # go through each p3d array and build the poeple
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
    # source: XNECT Matlab demo import
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
