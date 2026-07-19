# Ito application

`server/ito/` is the single Python application boundary. It hosts `client/`,
accepts the pilot endpoint, runs reconstruction, and owns one robot adapter.

Configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ITO_HOST` | `0.0.0.0` | HTTP/WebSocket bind address. |
| `ITO_PORT` | `8765` | Shared client and `/ws` port. |
| `ITO_ROBOT_BACKEND` | `local` | `local` or `remote`. |
| `ITO_CLIENT_DIR` | repository `client/` | Hosted WebXR assets. |
| `ITO_REQUEST_TIMEOUT_MS` | `5000` | Remote-driver request timeout. |

`LocalRobotAdapter` is the default in-process boundary. `RemoteRobotAdapter` is
the one-driver fallback for an external Ito deployment. A production local
integration supplies control, neutral-stop, emergency-stop, and safe-resumption
callbacks; the adapter enforces input timeout and newest-input rate limiting
inside the Ito process. It also supplies the reconstruction processor factory.
The stock image intentionally reports not-ready until a hardware integration is
wired instead of pretending to actuate a robot.
