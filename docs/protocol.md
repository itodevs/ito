# Ito protocol

Ito has one always-present network boundary and one optional boundary:

1. Pilot client ↔ Ito application (all deployments).
2. Ito application ↔ remote robot driver (external deployment only).

Local robot integration and reconstruction use calls, queues, and memory, not
this protocol.

## Envelope

WebSocket control messages are binary MessagePack maps:

| Field | Required | Meaning |
| --- | --- | --- |
| `protocolVersion` | yes | Exact value `ito.v1`. |
| `messageId` | yes | Correlation and diagnostics identifier. |
| `type` | yes | Message type below. |
| `payload` | yes | Message-specific map. |
| `replyToMessageId` | responses | Request being answered. |

There is no robot or control-session identifier. One endpoint represents one
configured robot and one active-control lifecycle.

Results use `{ok: true, value: {...}}` or
`{ok: false, reason: {code?, text?}}`.

## Pilot client protocol

The client opens `/ws` on the same origin that served it.

| Message | Direction | Purpose |
| --- | --- | --- |
| `connection.hello` | client → Ito | `{role: "pilotClient"}`. |
| `connection.hello.result` | Ito → client | Readiness, active state, and control configuration. |
| `control.start` | client → Ito | Explicitly begin control. |
| `control.start.result` | Ito → client | Confirms start and returns control configuration. |
| `control.stop` | client → Ito | Stop control with an optional Display Reason. |
| `control.stop.result` | Ito → client | Confirms the request was accepted. |
| `control.stopped` | Ito → client | Final stopped state and reason. |
| `robot.ready` | Ito → client | The configured robot became ready or unavailable. |
| `webrtc.offer` / `webrtc.answer` | either | Non-trickle signaling for a live path. |

Pilot live paths are:

- `pilotInput`: client-created unordered/unreliable data channel. Each UTF-8
  JSON snapshot contains `protocolVersion`, `sequence`, `timestampMs`,
  `headsetYawRad`, and a `controllers` list. It has no allocation identity.
- `splatBatches`: Ito-created reliable/ordered data channel carrying the binary
  Splat Batch format.

## Optional remote-driver protocol

The remote driver connects to the same `/ws` endpoint with
`{role: "remoteRobotDriver", ready: boolean}`. Only the configured remote
backend accepts this role, and only one driver may attach.

| Message | Direction | Purpose |
| --- | --- | --- |
| `driver.control.start` | Ito → driver | Enter the driver's active-control state. |
| `driver.control.start.result` | driver → Ito | Success or robot-local reason for failure. |
| `driver.control.stop` | Ito → driver | Enter the safe stopped state. |
| `driver.control.stop.result` | driver → Ito | Confirms local stop handling. |
| `webrtc.offer` / `webrtc.answer` | either | `pilotInput` negotiation or driver `cameraMedia` transport. |

`cameraMedia` is the optional remote-driver-to-Ito H.264 media path. In onboard
mode this path doesn't exist; frames enter reconstruction directly.

## Failure behavior

- Pilot disconnect: Ito stops control and invokes local safety immediately.
- Remote driver disconnect: Ito stops control; driver safety already acts
  locally without waiting for Ito.
- Stale pilot input: the adapter/driver uses its robot-specific timeout and
  safe response.
- Reconstruction or live-path failure: Ito stops control and sends a
  `control.stopped` reason without crashing the application.
