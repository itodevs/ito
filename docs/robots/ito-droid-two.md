# Ito Droid Two

Small humanoid robot inspired by the [Zeroth Bot (Z-Bot) by K-Scale Labs](https://kscalelabs.com/). Uses high-torque smart bus servos throughout, making it suitable for a walking humanoid form factor.

## Hardware

| Qty | Part |
|---|---|
| 1 | Raspberry Pi 5 (4GB) |
| 2 | Raspberry Pi Global Shutter Camera (IMX296) |
| 2 | Wide FOV C/CS-mount lens |
| 1 | [Waveshare Serial Bus Servo Driver HAT](https://www.waveshare.com/product/raspberry-pi/hats/motors-relays/bus-servo-driver-hat-a.htm) |
| n | [Waveshare ST3215 12V](https://www.waveshare.com/st3215-servo.htm?sku=22414) |
| 1 | 3S LiPo battery (11.1V nominal) |

The 3S LiPo connects directly to the Waveshare HAT's power input (11.1V nominal, 12.6V full charge — the ST3215 servos are rated 12V and handle this range fine). The HAT's onboard regulator provides 5V to the Pi via the GPIO header. No additional converters needed.

Active cooling is required on the Pi 5 to prevent thermal throttling under sustained load.

## Cameras

Stereo pair using two Pi Global Shutter cameras (IMX296, 1.6MP, 1456x1088) with wide FOV C/CS-mount lenses. Global shutter is important for SLAM accuracy during fast head motion.

The Pi 5 has two CSI connectors and supports hardware sync between cameras via the shutter sync line. See the [Pi camera sync docs](https://www.raspberrypi.com/documentation/accessories/camera.html#synchronous-captures).

Stereo calibration is done once per rig using OpenCV's stereo calibration routine with a checkerboard pattern.

## Software Stack

- **OS**: Ubuntu 24.04
- **ROS2**: Jazzy (LTS through 2029)
- **ROS2 nodes**: camera node (image_transport), servo/motor node (Waveshare serial bus protocol)
- **Camera streaming**: [web_video_server](https://github.com/RobotWebTools/web_video_server) (`ros-jazzy-web-video-server`)
- **Discovery**: mDNS via `_ito._tcp`

On a local network, ROS2 peer discovery is automatic. Over a VPN, the server sets `ROS_STATIC_PEERS` to the robot's address discovered via mDNS.
