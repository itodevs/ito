# Ito

Ito is immersive teleoperation software for one pilot operating one robot.

The normal deployment is one Python application running on the robot. It hosts
the WebXR pilot client, accepts pilot input, integrates with robot control and
sensors in-process, runs reconstruction, and streams binary scene updates back
to the pilot.

```text
Pilot WebXR client  <── network ──>  Ito application on robot
                                      ├── web hosting and WebRTC
                                      ├── local robot adapter
                                      ├── camera and sensor ingress
                                      └── reconstruction
```

Robots that cannot run Ito or reconstruction onboard use the same application
on an external machine. A lightweight remote driver stays on the robot for
sensor forwarding, actuation, and robot-local safety. The pilot still connects
to one Ito URL and sees the same controls.

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

See `docs/v1.md`, `docs/protocol.md`, and `docs/local-v1.md` for the current
design. Multi-user, multi-robot, discovery, allocation, and fleet coordination
are intentionally out of scope.
