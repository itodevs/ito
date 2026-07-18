# Ito Droid robot integration

Ito Droid keeps ROS-specific actuation and robot-local safety at the robot. Its
driver consumes the configured camera topic, maps newest pilot yaw to the
camera-pan servo, enforces a local input timeout, bounds motion, and neutralizes
on control stop or connection loss.

For the preferred onboard deployment, expose these camera/control seams through
a `LocalRobotAdapter` inside Ito. The lightweight external driver can also
attach to an external Ito application with `ITO_URL`; it receives pilot input
on a WebRTC data channel and publishes the configured ROS camera as H.264
WebRTC media.

Important configuration includes `ITO_URL`, `ITO_DROID_ROS_CAMERA_TOPIC`,
`ITO_DROID_ROS_SERVO_COMMAND_TOPIC`, `ITO_DROID_PILOT_INPUT_TIMEOUT_MS`, and the
servo limit/smoothing/resumption variables in `ito_droid/config.py`.
