# Ito Client

The Ito client is the pilot's immersive interface to a robot. Ito is built
entirely for human teleoperation rather than collecting demonstrations or
training AI. The client should make operating different kinds of robots feel
direct, capable, and comfortable.

It translates tracked headset and controller movement into input for the
selected robot driver. In the other direction, it turns robot sensor data or a
visual processor's scene into a comfortable 3D view of the robot's
surroundings. The same client is intended to pilot humanoids, droids, vehicles,
mechas, and other robot forms through their respective drivers.

The current client is a browser-based WebXR application built with A-Frame and SparkJS. It
connects directly to a robot driver and optionally a visual processor, renders
their output, and sends operator input to the driver.

The first implementation should prove the interaction and networking model. It
does not need to establish a stable client API.

## Target

The first target is a WebXR browser on the same Linux localhost as the
containerized services. LAN deployment and production hosting are later work.

## Desktop WebXR Emulation

The Meta Immersive Web Emulator can exercise the setup scene and controller
interaction without a headset. Its polyfilled `XRSession` is incompatible with
Chrome's native `XRWebGLBinding`, which A-Frame's Three.js r177 otherwise selects.
The client detects the emulator's `CustomWebXRPolyfill` marker and disables the
unused WebXR Layers path before entering VR, allowing Three.js to use the legacy
`XRWebGLLayer` path. This workaround is not applied on real headset sessions.

## Responsibilities

The client owns:

- loading a hardcoded list of service URLs;
- fetching each service's small `GET /` descriptor;
- showing available choices inside WebXR;
- establishing direct WebRTC connections;
- passing a driver's video-source connection information to a processor;
- rendering raw video or a processor scene;
- sampling headset and controller poses;
- enable and stop interaction;
- clearly showing connection, stale-data, and stop state.

It does not reconstruct scenes, relay video, or enforce the driver's final
safety behavior.

## Setup Scene

Show the browser-required `Enter Ito` button immediately. Fetch the hardcoded
service descriptors while waiting for the user gesture.

Inside WebXR:

1. Show reachable robot drivers as physical blocks.
2. Let the user tap a block with a controller-tip touch sphere.
3. Show raw view and the mock processor when their basic video kind/encoding
   match the selected driver.
4. Let the user tap a visual mode to connect.

Keep this data-driven, but do not build a general capability-negotiation engine.
For the first implementation, comparing the few descriptor fields that exist is
enough. Show a concise reason when the mock processor cannot use the selected
driver.

## Connection Setup

Every service exposes:

```text
GET  /
POST /webrtc
```

The client uses `POST /webrtc` to exchange an SDP offer and answer. The
established peer connection is the session. Closing it is teardown; there are no
REST session objects, leases, renewals, or status polling.

### Raw Mode

```text
client <-- video/status -- driver
client -- control -------> driver
```

Create one driver peer connection that includes its video track. Do not connect
to a processor.

Render mono video in a simple immersive surface. Show when frames become stale.
Calibration-perfect or stereo rendering is not required yet.

### Processed Mode

```text
client -- control -------> driver
client <-- status -------- driver
driver -- video ---------> processor
client <-- scene/status -- processor
```

1. Connect the client to the driver.
2. Connect the client to the processor.
3. Ask the driver for its video-source connection information over `status`.
4. Pass that information to the processor over `status`.
5. The processor connects directly to the driver.

The client never relays video or ongoing signaling between services.

## WebRTC Data

Use JSON for control and status messages while the implementation is changing.
The scene channel may carry binary data.

### Driver Connection

| Channel/track | Direction | Contents |
|---|---|---|
| `control` | client to driver | latest operator poses and enabled state |
| `status` | both | readiness, video-source information, errors, stop acknowledgement |
| video track | driver to client | raw mode only |

Send control at roughly 30 Hz. Each message contains:

- increasing sequence number;
- client monotonic timestamp;
- enabled state;
- required headset pose;
- optional left/right controller poses.

Use an unordered, non-retransmitting `control` channel if browser support allows
it. Old control messages are never useful.

### Processor Connection

| Channel | Direction | Contents |
|---|---|---|
| `scene` | processor to client | one Gaussian-splat PLY streamed as sequential binary chunks |
| `status` | both | video-source information, readiness, errors, resend request |

On the reliable ordered `scene` channel, receive a small JSON header followed by
sequential binary chunks. Write the chunks into one preallocated PLY buffer, then hand the completed
buffer to the A-Frame-compatible SparkJS release. If transfer fails, request the
whole stream again. Do not implement scene manifests,
revisions, stable chunk IDs, acknowledgements, or general resynchronization yet.

## Rendering And Loops

Keep the render loop independent from network callbacks. Render the newest
available state and mark it stale when updates stop.

The first implementation needs only:

1. the WebXR render loop;
2. a 30 Hz control-send loop;
3. WebRTC event/message handlers.

Do not add a general session manager, renewal loop, polling loop, or reconnect
framework yet.

## Control UX

Show simple immersive Enable and Stop controls. The recorded driver only logs
raw WebXR poses; coordinate alignment and robot-specific command conversion are
deferred until a physical driver exists.

Immediately stop sending enabled commands on:

- Stop;
- WebXR exit;
- lost focus;
- lost tracking;
- driver disconnection;
- client error.

Display the driver's stop acknowledgement. The driver watchdog remains the
authority that stops the robot if the client disappears.

## Status

Show only status useful for debugging the first implementation:

- driver and processor connection state;
- raw-video or processor-input freshness;
- processor readiness and input freshness;
- scene transfer state;
- whether control is enabled;
- latest driver stop acknowledgement.

Detailed WebRTC statistics, latency breakdowns, production health dashboards,
and partial-failure orchestration can be added after a working path exists.

## First Implementation

1. Enter WebXR and display hardcoded service blocks.
2. Establish a client-to-driver WebRTC connection.
3. Render direct raw video.
4. Send headset/controller poses and exercise Enable and Stop.
5. Establish a client-to-processor connection and pass it the driver's video
   connection information.
6. Render one incrementally streamed Gaussian-splat scene with SparkJS.

The code should remain easy to change. Prefer a small working path over
abstractions for services and modes that do not exist yet.
