# Ito Droid One

Ito Droid One is a physical robot concept for Ito, immersive teleoperation
software built entirely for human pilots. This document is hardware reference
material, not the current Ito driver contract or an implementation guide for
the first software version.

The current v1 target is described in `../../docs/v1.md`.

It is a simple, low-cost demo robot using hobby servos. It is intended as a
lightweight upper-body or non-walking humanoid. SG90 torque is not sufficient to
carry the Pi and battery through a walking gait, but works well for joints that
only move light 3D-printed parts.

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
