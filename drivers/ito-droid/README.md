# Ito Droid ROS Driver

This is the v1 Robot Driver for the physical Ito Droid target. It adapts
between Ito Protocol control-plane messages, direct pilot input snapshots, and
robot-local ROS camera and servo topics.

The driver is intentionally robot-side only: ROS topics and servo commands do
not leak into the Pilot Client, Ito Server, or Ito Protocol.

## Container

Build from the repository root:

```bash
docker build -f drivers/ito-droid/Dockerfile -t ito-droid-driver .
```

Run it on the robot or in a ROS network where the configured camera and servo
topics are available:

```bash
docker run --rm --network host \
  -e ITO_SERVER_URL=ws://ito-server.local:8765 \
  -e ITO_DROID_ROS_CAMERA_TOPIC=/image_raw \
  -e ITO_DROID_ROS_SERVO_COMMAND_TOPIC=/ito_droid/camera_pan/command \
  ito-droid-driver
```

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `ITO_SERVER_URL` | `ws://localhost:8765` | Ito Server WebSocket control URL. |
| `ITO_DROID_ROBOT_ID` | `ito-droid-1` | Stable robot identity reported to the server. |
| `ITO_DROID_NAME` | `Ito Droid` | Pilot-facing robot name. |
| `ITO_DROID_STATUS_INTERVAL_MS` | `1000` | Driver status/heartbeat interval. |
| `ITO_DROID_RECONNECT_INITIAL_DELAY_MS` | `250` | Initial reconnect backoff. |
| `ITO_DROID_RECONNECT_MAX_DELAY_MS` | `5000` | Maximum reconnect backoff. |
| `ITO_DROID_ROS_CAMERA_TOPIC` | `/image_raw` | ROS `sensor_msgs/Image` camera feed to consume. |
| `ITO_DROID_ROS_SERVO_COMMAND_TOPIC` | `/ito_droid/camera_pan/command` | ROS `std_msgs/Float64` camera-pan command topic, in degrees. |
| `ITO_DROID_ROS_NODE_NAME` | `ito_droid_driver` | ROS node name. |
| `ITO_DROID_PILOT_INPUT_TIMEOUT_MS` | `2000` | Missing pilot-input timeout before control loss. |
| `ITO_DROID_CONTROL_TICK_HZ` | `60` | Driver-owned control loop tick rate. |
| `ITO_DROID_SERVO_NEUTRAL_DEGREES` | `90` | Camera-pan neutral angle. |
| `ITO_DROID_SERVO_MIN_DEGREES` | `15` | Camera-pan lower limit. |
| `ITO_DROID_SERVO_MAX_DEGREES` | `165` | Camera-pan upper limit. |
| `ITO_DROID_YAW_TO_SERVO_DEGREES_PER_RADIAN` | `57.29577951308232` | Relative headset-yaw to servo-angle scale. |
| `ITO_DROID_SERVO_SMOOTHING` | `0.35` | Per-tick smoothing factor from current command toward target. |
| `ITO_DROID_SERVO_MAX_VELOCITY_DEGREES_PER_SECOND` | `180` | Normal correction velocity limit. |
| `ITO_DROID_RESUMPTION_INITIAL_VELOCITY_DEGREES_PER_SECOND` | `20` | Correction velocity immediately after recoverable control loss. |
| `ITO_DROID_RESUMPTION_RAMP_DURATION_MS` | `1500` | Duration for ramping correction velocity back to normal. |

## Current WebRTC State

The driver has explicit seams for:

- consuming ROS camera frames;
- handing frames to the driver-to-server camera media publisher;
- receiving Pilot Input Snapshots from the client-to-driver path.

The shared non-trickle WebRTC signaling and concrete H.264 media transport are
still covered by TODO 23, TODO 24, and TODO 26 in `../../docs/todo.md`.
