# Ito Droid One

Simple, low-cost demo robot using hobby servos. Intended as a lightweight upper-body or non-walking humanoid — SG90 torque is not sufficient to carry the Pi and battery through a walking gait, but works well for any joint that only moves light 3D-printed parts.

## Hardware

| Qty | Part |
|---|---|
| 1 | Raspberry Pi 5 (4GB) |
| 2 | Raspberry Pi Global Shutter Camera (IMX296) |
| 2 | Wide FOV C/CS-mount lens |
| 1 | PCA9685 16-channel PWM Servo HAT (I2C) |
| n | SG90 hobby servo |
| 1 | 3S LiPo battery (11.1V nominal) |
| 2 | 5V buck converter (BEC) |

The 3S LiPo feeds two buck converters: one for the Pi (via USB-C or GPIO 5V pin), one for the PCA9685 HAT's V+ servo rail. SG90s are rated 4.8–6V so the servo rail must be regulated down — the PCA9685 HAT passes V+ straight through to the servos with no onboard regulation. Two separate converters keeps servo current spikes off the Pi's supply.

## Cameras

Stereo pair using two Pi Global Shutter cameras (IMX296, 1.6MP, 1456x1088) with wide FOV C/CS-mount lenses. Global shutter is important for SLAM accuracy during fast head motion.

The Pi 5 has two CSI connectors and supports hardware sync between cameras via the shutter sync line. See the [Pi camera sync docs](https://www.raspberrypi.com/documentation/accessories/camera.html#synchronous-captures).

Stereo calibration is done once per rig using OpenCV's stereo calibration routine with a checkerboard pattern.

## Software Stack

- **OS**: Ubuntu 24.04
- **ROS2**: Jazzy (LTS through 2029)
- **ROS2 nodes**: camera node (image_transport), servo/motor node (PCA9685 over I2C)
- **Camera streaming**: [web_video_server](https://github.com/RobotWebTools/web_video_server) (`ros-jazzy-web-video-server`)
- **Discovery**: mDNS via `_ito._tcp`

On a local network, ROS2 peer discovery is automatic. Over a VPN, the server sets `ROS_STATIC_PEERS` to the robot's address discovered via mDNS.

## Installation

Install ROS:

```
sudo apt install ros-jazzy-ros-base
source /opt/ros/jazzy/setup.bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
```

Install the camera node:

```
sudo apt install ros-jazzy-camera-ros
```

Install the video server:

```
sudo apt install ros-jazzy-web-video-server
```

In a folder, create this launch program:

`nano launch.py`
```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='camera_ros',
            executable='camera_node',
            name='camera',
        ),
        Node(
            package='web_video_server',
            executable='web_video_server',
            name='web_video_server'
        ),
    ])
```

Then configure the program to run on startup:

`nano ito-droid-one.service`
```
[Unit]
Description=Ito Robot ROS2 nodes
After=network.target

[Service]
User=maarten
ExecStart=/bin/bash -c "source /opt/ros/jazzy/setup.bash && ros2 launch /home/maarten/dev/ito-droid-one/
launch.py"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
`sudo cp ./ito-droid-one.service /etc/systemd/system/ito-droid-one.service`
`sudo systemctl enable ito-droid-one --now`

Now the camera server is running! You can try it out at: http://<pi IP address>:8080/

