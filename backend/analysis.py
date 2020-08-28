from backend import analysis_base
import time
import json

mock_file_3d = "mock_data/ballet.json"
with open(mock_file_3d, 'r') as file:
    mock_data_3d = json.load(file)


def analyse_2d(video_id):
    # todo: send to openpose
    print("2d analysis for id %s started." % video_id)
    time.sleep(2)
    print("2d analysis for id %s finished." % video_id)
    # save model
    #model_2d.save()
    return mock_data_3d
