import time
import json
#import project.app as app
#from project.model import model
#from project.model.model import ResultType, ResultCode


def analyse(result_id):
    print("Starting analysis of %s" % result_id)
    ob = model.get_pending_results().first()
    if ob is None:
        return
    if ob.result_type == ResultType.dimension_2d:
        res =open_pose_analysis(ob)
    elif ob.result_type == ResultType.dimension_3d:
        res = three_d_baseline_analysis(ob)
    print("Analysis of %s finished." % result_id)
    app.notify_analysis()


def open_pose_analysis(mdl):
    print("sending to openpose executable")
    time.sleep(10)
    #mdl.result_code = ResultCode.success
    mdl.result_code = ResultCode.success
    app.db.session.commit()
    return True


def three_d_baseline_analysis(mdl):
    print("sending to 3d-pose-baseline executable")
    time.sleep(10)
    #mdl.result_code = ResultCode.success
    mdl.result_code = ResultCode.success
    #db.session.commit()
    return True
