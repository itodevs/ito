# Mock remote robot driver

This lightweight driver exercises the external-deployment fallback. It connects
to one Ito application, forwards a configured camera file over WebRTC, receives
pilot input, and logs snapshots. It has no identity, catalog status, heartbeat,
or allocation state.

Configuration:

- `ITO_URL` (default `ws://localhost:8765/ws`)
- `ITO_MOCK_ROBOT_CAMERA_VIDEO` (required for readiness)
- `ITO_MOCK_ROBOT_CAMERA_LOOP` (default `true`)
- `ITO_REMOTE_DRIVER_RECONNECT_INITIAL_DELAY_MS` (default `250`)
- `ITO_REMOTE_DRIVER_RECONNECT_MAX_DELAY_MS` (default `5000`)

Use the Compose `remote` profile described in `docs/local-v1.md`.
