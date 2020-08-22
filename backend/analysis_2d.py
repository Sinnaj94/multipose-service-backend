from backend import analysis_base
import time


def analyse_2d(video_id):
    # todo: send to openpose
    print("Analyse 2d started.")
    print("Analysing %s." % video_id)
    time.sleep(10)
    print("Analysis for %s finished." % video_id)
    return {"finished": True}
