# Ito

Ito is immersive teleoperation software built entirely for piloting robots.

Most teleoperation software treats the pilot experience as secondary. It is
usually a basic tool for collecting demonstrations and training robot policies.
Ito takes a different approach: it is not designed to train AI. Its sole purpose
is to make remotely operating a robot comfortable for the human pilot.

We envision a future where people pilot every type of robot from their home or
office. This could enable disabled people to act through robots in places their
bodies cannot easily take them, and allow people to explore or work in
environments that are hostile to humans.

Ito is intended to support humanoids, droids, vehicles, mechas, and robot forms
that do not fit an existing category. It translates the pilot's tracked pose and
controller input into control instructions appropriate to the piloted robot.
In the other direction, it translates the robot's sensor input into a
comfortable immersive 3D reconstruction of its surroundings.

## Codebase

WIP: the idea to separate all these things (processors, robot drivers) into separate programs that can each be docker containers, came from the observation that in order to have good support for (calibrated stereo) ROS camera feeds, you need rclpy which in turn needs a ROS installation, which is best solved using a docker container with ROS as the base image.

### Client

The WebXR client you use from your VR headset. Connects to a robot driver and processing software.

### Drivers

This directory contains driver implementations per robot type.

#### mock-robot

Mock robot driver. Its (mono) camera input is a video file. For testing purposes only.

#### ito-droid-one

(Future) ROS2 driver.

### Processors

Video processing software. Turns live camera footage into a 3D reconstruction.

#### mock-mono

Mock processing program that receives but ignores the robot's camera feed and instead streams a gaussian splat .ply file to the client. For testing purposes only.