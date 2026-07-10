# Mock Robot

The Mock Robot is Ito's robot-driver test double.

It speaks the Ito v1 WebSocket control plane as a Robot Driver, reports itself
to the Robot Catalog, accepts server-owned session lifecycle requests, logs
Pilot Input Snapshots to stdout, and opens a configured video file as mock
camera input. The local end-to-end tests exercise client-to-driver pilot input
over an `aiortc` WebRTC data channel. H.264 WebRTC publishing from the mock
camera file to the server remains covered by TODO 23.

## Configuration

Environment variables:

- `ITO_SERVER_URL`: Ito Server WebSocket URL. Default: `ws://localhost:8765`.
- `ITO_MOCK_ROBOT_ID`: stable mock robot identity. Default: `mock-robot-1`.
- `ITO_MOCK_ROBOT_NAME`: pilot-facing robot name. Default: `Mock Robot`.
- `ITO_MOCK_ROBOT_STATUS_INTERVAL_MS`: status heartbeat interval. Default:
  `1000`.
- `ITO_MOCK_ROBOT_CAMERA_VIDEO`: required video file path for an Available mock
  robot.
- `ITO_MOCK_ROBOT_CAMERA_CHUNK_SIZE`: file read chunk size used by the camera
  source. Default: `65536`.
- `ITO_MOCK_ROBOT_CAMERA_LOOP`: whether the file source loops at EOF. Default:
  `true`.

Run locally from the repository root:

```sh
PYTHONPATH=. python drivers/mock-robot/main.py
```

Build the container from the repository root:

```sh
docker build -f drivers/mock-robot/Dockerfile -t ito-mock-robot .
```

Run through Docker Compose with the local Ito Server and Pilot Client:

```sh
docker compose up --build
```

This uses `fixtures/mock-camera.mp4` by default. Override it with
`ITO_MOCK_ROBOT_CAMERA_VIDEO_HOST=/absolute/path/to/video.mp4` when needed.
