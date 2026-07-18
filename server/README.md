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
the one-driver fallback for an external Ito deployment.
