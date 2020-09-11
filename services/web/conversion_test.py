import argparse
from project.backend import analysis
from os import path
import sys
import progressbar
import time
import cv2
import importlib
import numpy as np
import os
from pathlib import Path
#from IPython.display import HTML

# Change this to your installation
VIDEO_PATH ='../../../video2bvh'
sys.path.append(path.abspath(VIDEO_PATH))

from pose_estimator_2d import openpose_estimator
from pose_estimator_3d import estimator_3d
from utils import smooth, vis, camera
from bvh_skeleton import openpose_skeleton, h36m_skeleton, cmu_skeleton


parser = argparse.ArgumentParser()
parser.add_argument("--video_path", help="Give the video path", default="../example_video.mp4")
parser.add_argument("--output_path", help="Give the output path", default="../output/")
parser.add_argument("--open_pose_models_path", help="Give the openpose models path", default='H:\Documents\openpose\models')
args = parser.parse_args()

# Set video file
video_file = Path(args.video_path)
output_dir = Path(f'{args.output_path}{video_file.stem}_cache')
open_pose_models_path = args.open_pose_models_path

print("Input file: %s, Output dir: %s" % (video_file, output_dir))


def prepare():
    if not output_dir.exists():
        os.makedirs(output_dir)

def analyse_2d(video_file, persist=True):
    # get model
    e2d = openpose_estimator.OpenPoseEstimator(model_folder=open_pose_models_path)
    
    
    cap = cv2.VideoCapture(str(video_file))
    video_length = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    keypoints_list = []
    img_width, img_height = None, None
    # progess bar visualizes
    bar = progressbar.ProgressBar(maxval=video_length, widgets=[progressbar.Bar('=', '[', ']'), ' ', progressbar.Percentage()])
    print("Beginning to analyse video %s" % str(video_file))
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
        
        i+=1
        bar.update(i)
    
    # save config to file
    config_file = Path(output_dir / 'config.npy')
    np.save(config_file, {'img_width': img_width, 'img_height': img_height, 'frames': video_length})
    print("\nFinished analysing %s" % video_file)
    cap.release()
    return keypoints_list


def analyse_3d(pose2d, conf):
    e3d = estimator_3d.Estimator3D(
            config_file='../../../models_3d/video_pose.yaml',
            checkpoint_file='../../../models_3d/converted.pt'
        )
    pose3d = e3d.estimate(pose2d, image_width=conf['img_width'], image_height=conf['img_height'])
    subject = 'S1'
    cam_id = '55011271'
    cam_params = camera.load_camera_params(f'{VIDEO_PATH}/cameras.h5')[subject][cam_id]
    R = cam_params['R']
    T = 0
    azimuth = cam_params['azimuth']
    
    # save config
    np.save(Path(output_dir / 'config_3d.npy'), {'subject':subject, 
                                                'cam_id': cam_id,
                                                'cam_params': cam_params,
                                                'R': R,
                                                'T': T,
                                                'azimuth': azimuth})

    pose3d_world = camera.camera2world(pose=pose3d, R=R, T=T)
    pose3d_world[:, :, 2] -= np.min(pose3d_world[:, :, 2]) #
    return pose3d_world


def export_gif(pose3d_world, video_file, config, fps=60):
    # TODO: Machen
    h36m_skel = h36m_skeleton.H36mSkeleton()
    ani = vis.vis_3d_keypoints_sequence(
        keypoints_sequence=pose3d_world[0:300],
        skeleton=h36m_skel,
        azimuth=config['azimuth'],
        fps=fps,
        #output_file=output_dir / 'test.mp4'
    )
    #output_file=gif_file


def main():
    prepare()
    pose2d = None
    pose2d_file = Path(output_dir / '2d_pose.npy')
    pose3d_file = Path(output_dir / '3d_pose.npy')
    pose3d_world = None
    keypoints_list = None
    if not pose2d_file.exists():
        print("Has not been analysed yet. analysing.")
        keypoints_list = analyse_2d(video_file)
        keypoints_list = smooth.filter_missing_value(
            keypoints_list=keypoints_list,
            method='ignore' # interpolation method will be implemented later
        )
        # smooth process will be implemented later
        # save 2d pose result
        pose2d = np.stack(keypoints_list)[:, :, :2]
        pose2d_file = Path(output_dir / '2d_pose.npy')
        np.save(pose2d_file, pose2d)
        
    else:
        print("NP 2d array found.")
        pose2d = np.load(pose2d_file)
    
    # 3d pose estimation
    # load config
    conf = np.load(Path(output_dir / 'config.npy'), allow_pickle=True).item()
    
    
    
    
    # estimate 3d pose
    #
    if not pose3d_file.exists():
        pose3d_world = analyse_3d(pose2d, conf)
        np.save(pose3d_file, pose3d_world)
    else:
        pose3d_world = np.load(pose3d_file)
    
    print("Analysis of 3d Finished. Saving the GIF")
    conf_3d = np.load(Path(output_dir / 'config_3d.npy'), allow_pickle=True).item()
    export_gif(pose3d_world, Path(output_dir / 'video.mp4'), conf_3d)
    print("Video saved. Exporting BVH File.")
    # TODO: Check data integrity
    bvh_file = output_dir / f'{video_file.stem}.bvh'
    cmu_skel = cmu_skeleton.CMUSkeleton()
    channels, header = cmu_skel.poses2bvh(pose3d_world, output_file=bvh_file)
    
    
    output = output_dir / 'h36m_cxk.bvh'
    h36m_skel = h36m_skeleton.H36mSkeleton()
    _ = h36m_skel.poses2bvh(pose3d_world, output_file=output)
    
    
    

main()