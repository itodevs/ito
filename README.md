# Ito

Ito is immersive teleoperation software built entirely for piloting robots.

Most teleoperation software treats the pilot experience as secondary. It is
usually a basic tool for collecting demonstrations and training robot policies.
Ito takes a different approach: it is not designed to train AI. Its sole purpose
is to make remotely operating a robot direct, capable, and comfortable for the
human pilot.

We envision a future where people pilot every type of robot from their home or
office. This could enable disabled people to act through robots in places their
bodies cannot easily take them, and allow people to explore, extract resources,
or perform rescue work in environments that are hostile to humans.

Ito is intended to support humanoids, droids, vehicles, mechas, and robot forms
that do not fit an existing category. It translates the pilot's tracked pose and
controller input into control instructions appropriate for the connected robot.
In the other direction, it translates the robot's sensor input into a
comfortable immersive 3D view of its surroundings.

The current implementation is the first step toward that vision. Its immediate
goal is to prove that a WebXR client can connect directly to a robot driver and
a visual processor, render useful feedback, and send operator poses safely. The
interfaces will change while implementation teaches us what is actually needed.

## Architecture

Ito has three component types:

1. The **WebXR client** renders the experience and sends operator input.
2. A **robot driver** exposes robot video and receives control.
3. A **visual processor** consumes robot video and produces a renderable scene.

```text
                         HTTP bootstrap
                  +----------------------+
                  |     WebXR client     |
                  +----------------------+
                    |                  ^
       pose/control |                  | scene
                    v                  |
             +-------------+     +------------------+
             | robot driver|---->| visual processor |
             +-------------+     +------------------+
                    | direct video
                    |
                    +-- raw video --> client
```

There is no central Ito server. Live data follows the shortest useful path:

- operator poses flow from the client to the robot driver;
- robot video flows directly to the client in raw-view mode;
- robot video flows directly to the visual processor in processed mode;
- scene data flows from the processor to the client.

The client starts and coordinates these direct connections. The driver remains
responsible for deciding what commands are accepted and for stopping when valid
control updates stop arriving.

## Keep The First Protocol Small

For now, a WebRTC peer connection is the session. Closing or losing it ends the
session and releases its resources.

Each service exposes only enough HTTP to establish a peer connection:

```text
GET  /
POST /webrtc
```

`GET /` returns a small JSON descriptor:

```json
{
  "name": "Recorded robot",
  "type": "robot-driver",
  "modes": ["control", "raw-video"],
  "video": {
    "kind": "mono",
    "encoding": "vp8"
  }
}
```

The descriptor is intentionally informal. It contains enough information for
the current client to display a service and decide whether the current mock
processor can use its video.

`POST /webrtc` accepts an SDP offer plus a small purpose/configuration object and
returns an SDP answer:

```json
{
  "purpose": "client",
  "offer": {
    "type": "offer",
    "sdp": "..."
  }
}
```

Possible purposes in the first implementation are:

- `client`: connect the WebXR client to a driver or processor;
- `video-source`: subscribe to a driver's video from a processor.

After setup, status, configuration, errors, control, and scene data use WebRTC
DataChannels. Video uses WebRTC media tracks. Control and status messages are
JSON; scene chunks may be binary.

Do not add a REST session API, leases, renewal endpoints, OpenAPI, Protobuf,
formal protocol version negotiation, or a general capability system yet. JSON
messages are sufficient while the message shapes are changing frequently.

When a concrete problem appears, solve it at the smallest useful layer and
document the reason. Stable schemas, authentication, discovery, reconnect
recovery, STUN/TURN deployment, and production hosting can be designed after the
first direct connections work.

## Connections

### Client To Driver

The client creates one peer connection to the selected driver.

| Channel/track | Direction | Contents |
|---|---|---|
| `control` DataChannel | client to driver | newest headset/controller poses and enabled state |
| `status` DataChannel | both | driver state, errors, and stop acknowledgement |
| video track | driver to client | raw-view mode only |

Control messages are disposable latest-value updates. They should not queue
behind older commands. Status messages may use the default reliable ordered
DataChannel behavior for the first implementation.

The driver sends the client its video-source connection information over
`status` when processed mode needs another peer to subscribe to its video. For
the recorded driver, this can be only its `/webrtc` URL and the
`video-source` purpose.

### Driver To Processor

The client passes the video-source connection information to the selected
processor over the processor's `status` channel. The processor then establishes
its own direct recv-only WebRTC connection to the driver.

The client does not relay video or SDP between the processor and driver after
passing that source descriptor.

### Client To Processor

The client creates one peer connection to the selected processor.

| Channel | Direction | Contents |
|---|---|---|
| `scene` | processor to client | scene bytes, split into messages if needed |
| `status` | both | configuration, readiness, errors, and simple resend request |

The first processor sends one mounted PLY scene over a reliable ordered
DataChannel. It sends a small JSON header followed by sequential binary chunks
because DataChannels have practical message-size limits. The client can request
the complete scene again if assembly fails. Do not build a general revision,
manifest, acknowledgement, or resynchronization protocol until a changing scene
exists.

## Raw View

Raw view is a client rendering mode, not a visual processor. It connects the
client directly to the driver's video track and creates no processor
connection.

This keeps the simplest useful path simple and avoids a service that only
forwards bytes.

## Coordinates And Control

The first implementation uses:

- right-handed coordinates;
- meters;
- positive Y up;
- negative Z forward;
- quaternion order `x, y, z, w`.

The mock driver logs WebXR poses directly. Coordinate conversion, transform
trees, and operator-to-robot alignment are required before controlling physical
hardware, but they are not needed to prove this recorded-driver path.

The driver owns the final safety behavior:

- it ignores out-of-order control updates;
- it accepts movement only while explicitly enabled;
- it stops when enabled updates stop arriving for 500 ms;
- it stops when the client connection closes.

The mock driver only logs accepted commands and stop events. It never addresses
physical hardware.

## Failure Behavior

Keep failure handling direct and visible:

| Failure | First-version behavior |
|---|---|
| Client-to-driver connection closes | driver performs `safe_stop` |
| Enabled control messages stop | driver performs `safe_stop` after 500 ms |
| Driver video stalls | client or processor shows stale/degraded state |
| Processor fails | client shows the failure and disables control if visual feedback is unsafe |
| Scene transfer fails | client requests the complete scene again |

Do not hide stale data or claim the robot stopped before the driver reports that
it stopped.

## Repository

This repository documents the shared architecture and coordinates independently
buildable implementations:

```text
client/                    WebXR client submodule
drivers/
  mock-robot/              recorded/mock driver submodule
  ito-droid/               physical robot concepts and reference material
processors/                visual processor implementations
mvp.md                     first implementation prompt
```

`drivers/ito-droid/` is reference material and a future integration target. The
first implementation uses `drivers/mock-robot/` and does not control physical
hardware.

## First Implementation

1. Prove a Windows WebXR browser can establish direct WebRTC connections to
   services running in WSL2.
2. Implement the recorded driver and direct raw-video client view.
3. Send headset/controller poses to the driver and prove the watchdog stops on
   missing updates.
4. Implement the mock processor, direct driver-to-processor video, and one PLY
   scene transfer to the client.
5. Use what was learned to decide which message schemas and operational
   features deserve stable designs.

## Deferred Until Needed

- stable public APIs and generated schemas;
- authentication and authorization;
- service discovery and editable service configuration;
- production HTTPS, CORS policy, STUN, and TURN;
- session leases and reconnect recovery;
- general compatibility negotiation;
- coordinate-frame composition, alignment, and command limits;
- stereo, RGB-D, ROS2, and real reconstruction;
- scene revisions, spatial chunks, LOD, and persistent map recovery;
- comprehensive metrics and recording.

These are plausible future requirements, not requirements for writing the first
working code.

## Run the MVP

The root Compose application starts the recorded driver, mock mono processor,
and HTTPS WebXR client. Copy `.env.example` to `.env`, set absolute paths to a
seekable video and valid PLY file, then run:

```bash
docker compose up --build
```

Open `https://localhost:8443` from the PCVR browser (or use the WSL address),
accept the development certificate, and select the recorded robot. The raw path
connects the browser directly to the driver. The processed path asks the
processor to connect directly to the driver and sends the mounted PLY back to
the browser. Ports 8001 and 8002 also listen on the WSL host to help diagnose direct
WebRTC connectivity.

For component development and tests:

```bash
cd client && npm install && npm test && npm run build
python -m pip install -r drivers/mock-robot/requirements.txt pytest
(cd drivers/mock-robot && pytest)
python -m pip install -r processors/mock-mono/requirements.txt pytest
(cd processors/mock-mono && pytest)
```
