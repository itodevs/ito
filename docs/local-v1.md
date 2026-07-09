# Local v1 Operation

This guide covers local Ito v1 operation with Docker Compose or Podman Compose. It keeps the
same boundaries as `docs/v1.md`: the Pilot Client is static web content, the Ito
Server owns catalog/session/reconstruction authority, and robot drivers connect
outward over the Ito Protocol WebSocket control plane.

## Compose Services

- `ito-server`: Python Ito Server on `ws://localhost:8765`.
- `pilot-client`: nginx static hosting for `client/` on
  `http://localhost:8080`.
- `mock-robot`: Mock Robot driver. It starts by default and uses
  `fixtures/mock-camera.mp4` when present.
- `ito-droid`: optional profile-backed physical Ito Droid ROS driver. It is
  intended for robot-side use with host networking and an existing ROS camera
  feed/servo command path.

## Local Stack

Build and run the local server, Pilot Client, and Mock Robot:

```sh
docker compose up --build
# or, with Podman Compose:
podman compose up --build
```

The Compose file uses Podman's pre-existing external `podman` network instead of
a project-created bridge network. This keeps local Podman operation independent
of `aardvark-dns`/user-bus startup. The Mock Robot reaches the Ito Server through
`host.containers.internal:8765`; Docker users can still use the same Compose file
because the server port is published to the host.

Open `http://localhost:8080/`. The client defaults to the Ito Server control
WebSocket at `ws://<page-host>:8765`, which is `ws://localhost:8765` for this
Compose setup.

Stop and remove local containers:

```sh
docker compose down
# or:
podman compose down
```

## Mock Robot Video

By default, the Mock Robot mounts `fixtures/mock-camera.mp4`. To use a
different local video file, override `ITO_MOCK_ROBOT_CAMERA_VIDEO_HOST`:

```sh
ITO_MOCK_ROBOT_CAMERA_VIDEO_HOST=/absolute/path/to/mock-camera.mp4 \
  docker compose up --build
# or:
ITO_MOCK_ROBOT_CAMERA_VIDEO_HOST=/absolute/path/to/mock-camera.mp4 \
  podman compose up --build
```

Useful log streams while testing acquisition and pilot input:

```sh
docker compose logs -f ito-server mock-robot
# or:
podman compose logs -f ito-server mock-robot
```

The Mock Robot exercises the v1 WebSocket control plane, acquisition/session
lifecycle, and client-to-driver pilot-input WebRTC data channel. Driver-to-server
H.264 WebRTC camera publishing remains tied to TODO 23, so local Mock Robot
operation does not yet prove camera media ingestion into reconstruction.

## Ito Droid

Run the physical Ito Droid driver on the robot or in the robot's ROS network.
The environment must already provide the configured ROS camera topic and servo
command topic.

```sh
ITO_SERVER_URL=ws://<server-host-or-ip>:8765 \
ITO_DROID_ROS_CAMERA_TOPIC=/image_raw \
ITO_DROID_ROS_SERVO_COMMAND_TOPIC=/ito_droid/camera_pan/command \
  docker compose --profile droid up --build ito-droid
```

Because the `ito-droid` service uses host networking, `ITO_SERVER_URL` must be
reachable from the robot host. The ROS topic names must match the robot-local
ROS graph; ROS setup and camera-driver bring-up are outside Ito v1.

## Local Test Commands

Python tests:

```sh
python -m pip install -r server/requirements.txt -r drivers/mock-robot/requirements.txt
pytest -q
```

`aiortc` and PyAV are required for the WebRTC/H.264 paths. If PyAV builds from
source instead of installing a wheel, the host needs FFmpeg development
libraries available through `pkg-config`; otherwise tests that require `aiortc`
will be skipped or dependency installation will fail.

Pilot Client tests:

```sh
cd client
npm test
```
