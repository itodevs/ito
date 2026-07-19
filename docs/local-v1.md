# Local deployment

## Default onboard-shaped mode

Start one application/container:

```bash
docker compose up --build ito
```

Open `http://localhost:8765/`. The application serves the client and accepts its
WebSocket at `ws://localhost:8765/ws`. No nginx or reverse proxy is required.

The default `ITO_ROBOT_BACKEND=local` uses the in-process adapter. Production
robot code supplies its control sink, safe-stop callback, and sensor frames.

## External-driver fallback

Provide an H.264 sample file and start the remote profile:

```bash
ITO_ROBOT_BACKEND=remote \
ITO_MOCK_ROBOT_CAMERA_VIDEO_HOST=/absolute/path/to/camera.mp4 \
docker compose --profile remote up --build
```

The browser still opens `http://localhost:8765/`. Only the configured last hop
changes: Ito connects through its remote adapter to the lightweight driver.

## Checks

```bash
docker compose config
curl --fail http://localhost:8765/
```

The development and test workflow uses `.devcontainer/`; don't install project
tools on the host.
