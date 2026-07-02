# Use WebSocket for control-plane IPC and WebRTC for live data

Ito v1 uses WebSocket for IPC between Pilot Client, Ito Server, and Robot Driver: catalog request/response, robot-driver status/heartbeat, acquisition, session lifecycle, displayable errors/reasons, and WebRTC offer/answer signaling. The static Pilot Client can be hosted separately, such as by nginx; HTTP is not an Ito application IPC surface in v1.

Control-plane messages use a common MessagePack-encoded envelope over binary WebSocket frames. This gives Ito one compact structure for version checks, message type routing, logging, and request/response correlation.

Robot drivers send status/heartbeat every 1 second by default. The server marks a robot Unavailable if the driver WebSocket disconnects or if no fresh status/heartbeat arrives within 2 seconds by default. Both values are configurable, and the server evaluates liveness proactively rather than waiting for a client catalog request.

WebRTC remains the live data/media plane: Pilot Client ↔ Robot Driver for pilot input, Robot Driver ↔ Ito Server for H.264 camera media, and Ito Server ↔ Pilot Client for Splat Batches. This keeps low-latency streams on WebRTC while giving the server an immediate reliable path to tell the driver to start/end sessions and to notify the client of lifecycle events.
