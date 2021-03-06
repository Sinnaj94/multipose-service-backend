// xnect.cpp : Defines the entry point for the console application.
//
#include <chrono>
#include <thread>
#include <cstdlib>
#include "xnect.hpp"
#include "opencv2/opencv.hpp"
#include "mongoose.h"
#define WEB_CAM 0

std::string videoFilePath = "";

using namespace cv;

// Draw the bones (from XNECT)
void drawBones(cv::Mat &img, XNECT &xnect, int person)
{
	int numOfJoints = xnect.getNumOf3DJoints();

	for (int i = 0; i < numOfJoints; i++)
	{
		int parentID = xnect.getJoint3DParent(i);
		if (parentID == -1 ) continue;
		// lookup 2 connected body/hand parts
		cv::Point2f partA = xnect.ProjectWithIntrinsics(xnect.getJoint3DIK(person,i));
		cv::Point2f partB = xnect.ProjectWithIntrinsics(xnect.getJoint3DIK(person, parentID));


		if (partA.x <= 0 || partA.y <= 0 || partB.x <= 0 || partB.y <= 0)
			continue;

		line(img, partA, partB, xnect.getPersonColor(person), 4);

	}

}
void drawJoints(cv::Mat &img, XNECT &xnect, int person)
{

	int numOfJoints = xnect.getNumOf3DJoints() - 2; // don't render feet, can be unstable

	for (int i = 0; i < numOfJoints; i++)
	{
		int thickness = -1;
		int lineType = 8;
		cv::Point2f point2D = xnect.ProjectWithIntrinsics(xnect.getJoint3DIK(person, i));
		cv::circle(img, point2D, 6, xnect.getPersonColor(person), -1);

	}
}

void drawPeople(cv::Mat &img, XNECT &xnect)
{
	for (int i = 0; i < xnect.getNumOfPeople(); i++)
       if (xnect.isPersonActive(i))
	     {
	     	drawBones(img, xnect,i);
	     	drawJoints(img, xnect,i);
	     }

}
bool playLIVE(XNECT &xnect)
{
	cv::VideoCapture cap;

	if (!cap.open(0))
	{
		std::cout << "Can't open webcam!\n";
		cv::waitKey(0);
		return false;
	}
	if (!(cap.set(CV_CAP_PROP_FRAME_WIDTH, xnect.processWidth) && cap.set(CV_CAP_PROP_FRAME_HEIGHT, xnect.processHeight)))
	{

		std::cout << "[ ERROR ]: the connected webcam does not support " << xnect.processWidth << " x " << xnect.processHeight << " resolution." << std::endl;
		cv::waitKey(0);
		return false;
	}
	// open the default camera, use something different from 0 otherwise;
	// Check VideoCapture documentation.


	for (;;)
	{
		cv::Mat frame;
		cap >> frame;
		if (frame.empty()) break; // end of video stream
		xnect.processImg(frame);

		xnect.sendDataToUnity();
		drawPeople(frame, xnect);

		cv::namedWindow("liveWebCam", cv::WINDOW_NORMAL);
		imshow("liveWebCam", frame);

		char ch = cv::waitKey(1);


		if (ch == 27) break; // stop capturing by pressing ESC

		if (ch == 'p' || ch == 'P')
		{
			xnect.rescaleSkeletons();
			std::cout << "rescaling" << std::endl;

		}

		if (ch == 'r' || ch == 'R')
		{
			xnect.resetSkeletons();
			std::cout << "resetting" << std::endl;
		}


	}
	// the camera will be closed automatically upon exit

	return true;
}

void analyseVideo(std::string &videoFilePath, XNECT &xnect)
{
    std::cout << "[ANALYSIS] " << videoFilePath << std::endl;

    VideoCapture cap(videoFilePath); // open the video file
    if(!cap.isOpened())  // check if we succeeded
        CV_Error(CV_StsError, "Can not open Video file");

    //cap.get(CV_CAP_PROP_FRAME_COUNT) contains the number of frames in the video;
    int index = 0;
    while(1)
    {
        Mat frame;
        cap >> frame; // get the next frame from video
        if(frame.empty())
            break;
        if(index == 0) {
            xnect.processHeight = cap.get(CAP_PROP_FRAME_HEIGHT);
            xnect.processWidth = cap.get(CV_CAP_PROP_FRAME_WIDTH);
        }
        index++;
        xnect.processImg(frame);
        //xnect.sendDataToUnity();
        //drawPeople(frame, xnect);
        //namedWindow("main", WINDOW_NORMAL);
        //imshow("main", frame);
        //waitKey(1);
    }
    cap.release();

    std::cout << "Finished analysis..." << std::endl;
}

int main(int argc, char **argv)
{
	std::cout << "Starting XNECT" << argc << std::endl;
	// Check if image path is given
	if (argc <= 1) {
		std::cout << "Please give the image path (example: ./XNECT <path_to_video>)" << std::endl;
		return 1;
	}
	videoFilePath = argv[1];
	std::cout << "Working dir: " << videoFilePath << std::endl;

	std::string video = videoFilePath + "/video.mp4";
    // Check if only a certain number of frames should be analysed (for debugging)
	int num_frames = -1;
	if(argc == 3) {
		std::cout << "Analysing first " << argv[2] << " frames." << std::endl;
		num_frames = atoi(argv[2]);
	}
	XNECT xnect;
	// Analyse the video in xnect
    analyseVideo(video, xnect);
    // Save joint and raw joint positions
	xnect.save_joint_positions(videoFilePath);
	xnect.save_raw_joint_positions(videoFilePath);

	return 0;
}
