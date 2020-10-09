// xnect.cpp : Defines the entry point for the console application.
//
#include <chrono>
#include <thread>
#include <cstdlib>
#include "xnect.hpp"

#define WEB_CAM 0

std::string images_to_load = "";


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
void readImageSeq(XNECT &xnect, int num_frames)
{
	vector<cv::String> fn;
	cv::glob(images_to_load + "/*.jpeg", fn, false);

	vector<cv::Mat> images;
	std::cout << num_frames << " (num_frames...)" << std::endl;
	size_t count = fn.size();
	if(num_frames > -1) {
		count = num_frames;
		std::cout << count << " (count...)" << std::endl;
	}

	for (int i = 0; i < count; i++)
	{
		cv::Mat currentImage = imread(fn[i]);

		xnect.processImg(currentImage);

  		//xnect.sendDataToUnity();
		drawPeople(currentImage, xnect);

		cv::namedWindow("main", cv::WINDOW_NORMAL);
		imshow("main", currentImage);
		cv::waitKey(1);
		//std::cout << xnect.getUnityData() << std::endl;
		//std::this_thread::sleep_for(std::chrono::milliseconds(100));
	}
}

int main(int argc, char **argv)
{
	std::cout << "Starting XNECT" << argc << std::endl;
	if (argc <= 1) {
		std::cout << "Please give the image path (example: ./XNECT <path-to-imgs>)" << std::endl;
		return 1;
	}
	images_to_load = argv[1];
	std::cout << "Working dir: " << images_to_load << std::endl;
	int num_frames = -1;
	if(argc == 3) {
		std::cout << "Analysing first " << argv[2] << " frames." << std::endl;
		num_frames = atoi(argv[2]);
	}
	XNECT xnect;


	if (WEB_CAM)
	{
		if (playLIVE(xnect) == false)
			return 1;
	}
	else
		readImageSeq(xnect, num_frames);


	xnect.save_joint_positions("./output");
	xnect.save_raw_joint_positions("./output");

	return 0;
}
