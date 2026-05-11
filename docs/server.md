# Ito Server

Python-based server that runs on the operator's PC. It receives camera frames from the robot, performs 3D reconstruction, and streams the result to the Ito client.

## Role in the Stack

The server decouples the operator's head rotation from the robot's camera. Because the robot is on WiFi or cellular, video frames arrive with meaningful latency. Instead of displaying the raw video feed, the server builds a 3D scene from the incoming frames. The client renders that scene from the operator's current head pose at 90Hz, independent of when new frames arrive. The 3D reconstruction is the latency compensation mechanism.

The server runs on the operator's PC (GPU machine). The robot streams camera data to it; the server streams the reconstructed scene to the client. The client streams operator pose to the server, which passes it on to the robot.

## Reconstruction Algorithms

| Algorithm | Mono | Stereo | RGB-D | Output | Speed |
|---|---|---|---|---|---|
| ORB-SLAM3 | yes | yes | yes | Camera poses + sparse point cloud | fastest |
| MonoGS | yes | yes | yes | Gaussian splats | moderate (~10fps) |
| SplaTAM | no | no | yes | Gaussian splats | moderate |
| GI-SLAM | yes | yes | yes | Gaussian splats | moderate |
| WildGS-SLAM | yes | no | no | Gaussian splats (handles dynamic environments) | slow |
| MAST3R-SLAM | yes | no | no | Dense point maps | slow |
| MAST3R | no | yes | no | Dense point maps | slowest |

## SLAM / Reconstruction Stack

The recommended architecture is a hybrid:

- **ORB-SLAM3** as the tracking front end: battle-tested, supports mono, stereo, and RGB-D. Handles loop closure and relocalization. Outputs camera poses per keyframe.
- **3D Gaussian Splatting map** as the back end: consumes poses from ORB-SLAM3 and builds a renderable scene. Candidates: MonoGS, GI-SLAM (both support mono and stereo).

This split means tracking and mapping are decoupled. If ORB-SLAM3 loses tracking briefly, the map is unaffected. Loop closures from ORB-SLAM3 propagate updated poses into the Gaussian map's keyframe anchors.

For stereo input, ORB-SLAM3 stereo mode gives metric scale for free. For mono input, scale is ambiguous without an IMU.

## Gaussian Splat Representation

View-dependent color (spherical harmonics) is not needed. The operator's viewpoint is always close to the robot camera's viewpoint (the robot attempts to match the operator's head pose). Drop SH entirely and use RGB-only per splat. This significantly reduces per-splat data size and bandwidth.

Per-splat data (RGB-only): position (3x f32), scale (3x f16), rotation quaternion (4x f16), opacity (1x f16), color (3x u8). Roughly 28 bytes per splat.

## Streaming to Client

Transport: **WebRTC DataChannel** via `aiortc`. Unreliable/unordered mode is preferred (a stale SLAM frame is worse than a dropped one), and WebRTC handles NAT traversal without extra infrastructure.

Protocol: send splat **deltas** (added, removed, modified splat indices) rather than full snapshots each frame. Include a keyframe message so a freshly connected client can resync. A small binary header per message: frame ID, timestamp, payload type, byte counts.

## Robot Interface

ROS2 is a first class citizen in Ito. The server runs a ROS2 node via **rclpy** and communicates with ROS2 robots natively — no bridge or JSON translation layer. Camera frames, joint state, and control topics are all handled directly over ROS2.

For non-ROS robots, each supported robot family has a **driver sidecar**: a small separate process that speaks the robot's native protocol (Unitree SDK2, MAVLink, plain UDP, etc.) and exposes a standard Ito interface to the server. The server only talks to the driver; it does not need to know the underlying protocol.

### Discovery

| Network | Method |
|---|---|
| Local network | mDNS — robots advertise as `_ito._tcp`, server discovers automatically |
| VPN | mDNS discovers the robot's VPN address; server sets `ROS_STATIC_PEERS` to connect directly |

Both ROS2 robots and driver sidecars participate in the same discovery mechanism. Both machines must share the same `ROS_DOMAIN_ID`.

### Camera Streams

Camera streaming from ROS2 robots is handled by [web_video_server](https://github.com/RobotWebTools/web_video_server), which exposes ROS2 camera topics as HTTP video streams. The server subscribes to these streams via rclpy and feeds frames into the SLAM pipeline.
