# Ito

Ito is immersive teleoperation software built entirely for piloting robots.

Most teleoperation software treats the pilot experience as secondary. It is usually a basic tool for collecting demonstrations and training robot policies. Ito takes a different approach: it is not designed to train AI. Its sole purpose is to make remotely operating a robot comfortable for the human pilot. We envision a future where people pilot every type of robot from their home or office. This could enable disabled people to act through robots in places their bodies cannot easily take them, and allow people to explore or work in environments that are hostile to humans. Ito is intended to support humanoids, droids, vehicles, mechas, and robot forms that do not fit an existing category. It translates the pilot's tracked pose and controller input into control instructions appropriate to the piloted robot. In the other direction, it translates the robot's sensor input into a comfortable immersive 3D reconstruction of its surroundings.

## Run

The default Compose deployment starts one container and serves the client at
`http://localhost:8765/`:

```bash
docker compose up --build ito
```

The default local adapter is an in-process integration seam. Robot-specific
code supplies `ReconstructionFrame` values through
`LocalRobotAdapter.publish_sensor_frame()` and receives pilot snapshots through
its control sink. The adapter owns pilot-input timeout, newest-input rate
limiting, neutral stop, and an emergency-stop latch; robot-specific callbacks
provide the actual actuation and neutralization. No loopback transport is
involved.

The stock container has no robot-specific hardware binding and therefore
reports the local robot as not ready. A robot image wires the adapter callbacks
and a `ReconstructionProcessor` factory into the same `ItoApplication`; this is
still one process and introduces no local network boundary.

For the external-driver fallback:

```bash
ITO_ROBOT_BACKEND=remote docker compose --profile remote up --build
```

Set `ITO_MOCK_ROBOT_CAMERA_VIDEO_HOST` to an H.264 sample file when using the
mock remote driver.

## Codebase

- `server/ito/`: the Ito application and its local/remote robot adapters.
- `server/processors/`: in-application reconstruction algorithms.
- `client/`: the WebXR pilot client served by Ito.
- `drivers/`: lightweight remote-driver implementations for external mode.
- `docs/`: product, protocol, deployment, and architectural decisions.
