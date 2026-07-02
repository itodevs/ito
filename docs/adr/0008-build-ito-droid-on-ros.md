# Build Ito Droid on ROS

Ito Droid uses ROS as its robot software platform because it provides a widely adopted ecosystem for cameras, actuators, and future robot capabilities. Its robot driver adapts between Ito and ROS; ROS concepts do not become requirements of Ito's client, server, or protocol, so non-ROS robots remain first-class integration targets.

The Ito Droid driver is deployed as a container built on a ROS base image. It participates in the robot's ROS graph and consumes existing ROS topics for sensor feeds, such as camera frames, instead of owning camera setup itself. The driver is configured through Docker Compose environment variables, including the Ito Server URL, ROS topic names, pilot-input timeout, servo neutral angle, servo limits, smoothing, and control-resumption ramp rates. This keeps Ito's responsibility at the teleoperation integration boundary while letting robot-specific ROS packages handle device drivers and hardware bring-up.
