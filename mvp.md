# Ito First-Version Implementation Prompt

## Goal

Build the smallest working Ito vertical slice described by `README.md` and
`client/README.md`.

A user must be able to enter WebXR, select a recorded robot driver, choose raw
video or a mock visual processor, see useful output, and send safely watched
headset/controller poses to the driver.

This first-version implementation is experimental. Ito's purpose is not. Build
the smallest useful proof of Ito's immersive robot-piloting experience, and
optimize its code for learning and ease of change rather than API stability or
hypothetical future deployments.

Preserve only the central architectural decisions:

- there is no central Ito server;
- live data uses direct WebRTC connections;
- raw view connects the driver directly to the client;
- processed view connects the driver directly to the processor and the
  processor directly to the client;
- the driver owns the final 500 ms control watchdog.

## Repository Boundaries

Work with the existing repository:

```text
README.md
mvp.md
client/                    WebXR client submodule
drivers/
  mock-robot/              recorded/mock robot-driver submodule
  ito-droid/               physical robot concepts and reference material
processors/                visual processor implementations
```

- Implement the client in `client/`.
- Implement the recorded driver in `drivers/mock-robot/`.
- Add the mock processor under `processors/mock-mono/`.
- Keep each component independently buildable.
- Add root `compose.yaml` and `.env.example` for the local demo.
- Do not modify `drivers/ito-droid/` or control physical hardware.
- Do not create a central server, shared service framework, generated protocol
  package, or speculative abstraction layer.

## Minimal Protocol

For the first implementation, a WebRTC peer connection is the session. When it
closes, release its resources.

Each driver and processor exposes:

```text
GET  /
POST /webrtc
```

`GET /` returns an informal JSON descriptor containing only fields currently
used by the client, such as:

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

`POST /webrtc` accepts a purpose/configuration object and SDP offer, then returns
an SDP answer. Use one-shot signaling after ICE gathering.

After connection:

- video uses WebRTC media tracks;
- all other messages use DataChannels;
- control/status/configuration/error messages are JSON;
- those messages use `control` and `status` channels;
- operator poses use a `control` channel;
- processor output uses a reliable ordered `scene` channel and may be binary.

Do not implement:

- REST session resources, status endpoints, deletion, leases, or renewal;
- OpenAPI or Protobuf;
- formal protocol versions or stable error-code catalogs;
- authentication or authorization;
- a general capability/compatibility system;
- reconnect orchestration or a persistent scene synchronization protocol.

The recorded driver has only one video source, so the processor only needs its
`/webrtc` URL and the `video-source` purpose. Do not add source tokens yet.

## Technologies

- Client: vanilla JavaScript, Vite, Three.js, `@sparkjsdev/spark`.
- Services: Python 3.12, FastAPI, aiortc, PyAV.
- Local client hosting and optional same-origin signaling proxy: Nginx.
- Local orchestration: Docker Compose.

Pin direct dependencies, but do not spend time building shared packaging or
code-generation infrastructure.

## Local Deployment

The required target is a Windows PCVR browser through Virtual Desktop, with the
services and development commands running in WSL2.

Bind-mount:

- `VIDEO_FILE` into the recorded driver;
- `SPLAT_FILE` into the mock processor.

First prove that the Windows browser can establish WebRTC media and DataChannel
connections to services in WSL2. Log ICE candidates and selected candidate
pairs while diagnosing that path.

Use the simplest local hosting setup that lets the target browser enter WebXR.
Production HTTPS, CORS, STUN, TURN, LAN access, and public hosting are out of
scope unless one becomes necessary to make this local path work.

Nginx may proxy HTTP signaling. It must not proxy RTP or DataChannel traffic.

## Recorded Robot Driver

Implement in `drivers/mock-robot/`.

- Probe and loop one mounted seekable video with
  `MediaPlayer(..., loop=True)`.
- Offer a browser-compatible mono WebRTC video track.
- Use `MediaRelay` so raw view and the processor can subscribe concurrently.
- Return a small descriptor from `GET /`.
- Accept client and video-source offers through `POST /webrtc`.
- Create `control` and `status` DataChannels for the client connection.
- Send simple video-source connection information over `status` when requested.
- Receive operator pose messages at about 30 Hz and log accepted commands.
- Ignore stale or out-of-order control messages.
- Require explicit enable before treating poses as active commands.
- Perform and log `safe_stop` when:
  - an enabled update has not arrived for 500 ms;
  - the client sends disabled/stop;
  - the client peer connection closes.
- Send a stop acknowledgement over `status`.
- Log enough connection, frame, command, and watchdog information to debug the
  demo.

Do not address physical servos or depend on `drivers/ito-droid/`.

## Mock Mono Processor

Implement under `processors/mock-mono/`.

- Return a small descriptor from `GET /` stating that it accepts the recorded
  driver's mono video and outputs a PLY scene.
- Accept the client offer through `POST /webrtc`.
- Receive the driver's video-source connection information over `status`.
- Establish a direct recv-only WebRTC connection to the driver.
- Continuously consume video frames and count them.
- Report ready only after receiving the first frame.
- Report stale/degraded when frames stop.
- Read and validate the mounted PLY at startup.
- Send a small JSON header and then the PLY over `scene` as sequential binary
  chunks small enough for DataChannel messages.
- On a simple resend request, send the whole PLY again.
- Log enough frame, scene-transfer, and connection information to debug the
  demo.

Do not implement reconstruction, changing scenes, manifests, revisions,
acknowledgements, or persistent resynchronization.

## Client

Implement in `client/` and follow `client/README.md`.

- Build a real WebXR client with no frontend framework or TypeScript.
- Display `Enter Ito` immediately.
- Load hardcoded driver and processor URLs.
- Fetch their `GET /` descriptors while waiting for the user gesture.
- Show reachable drivers as tappable physical blocks.
- After driver selection, show raw view and the mock processor when their basic
  video descriptor fields match.
- Use visible controller-tip touch spheres and contact debounce.
- In raw mode:
  - connect only to the driver;
  - render its direct video track;
  - show stale-video state.
- In processed mode:
  - connect to the driver and processor;
  - request video-source connection information from the driver;
  - pass it to the processor;
  - render the PLY received from the processor with Spark.
- Reassemble sequential scene chunks. Request the complete scene again if
  transfer fails.
- Sample and send headset plus available controller poses at about 30 Hz.
- Show simple immersive Enable and Stop controls.
- Stop sending enabled commands on Stop, XR exit, lost focus, lost tracking,
  driver disconnect, or client error.
- Show connection state, visual freshness, enabled state, and latest
  stop acknowledgement.

Keep the render loop independent from WebRTC callbacks. Do not build a general
session manager, health system, compatibility engine, or reconnect framework.

## JSON Message Guidance

Use direct, readable JSON objects for control and status. Add a `type` field and
only the data needed by the current sender and receiver. Scene bytes may remain
binary.

Example control message:

```json
{
  "type": "control",
  "sequence": 42,
  "sentAtMs": 123456.7,
  "enabled": true,
  "head": {
    "position": [0, 1.7, 0],
    "rotation": [0, 0, 0, 1]
  }
}
```

Use right-handed coordinates, meters, positive Y up, negative Z forward, and
quaternion order `x, y, z, w`.

Do not create a shared schema package yet. Keep sender and receiver fixtures in
their component tests so message changes remain easy.

## Tests

Write tests for behavior that can break the first demo:

- each service descriptor and WebRTC signaling endpoint;
- driver video delivery to a raw-view peer;
- driver video delivery to the processor;
- processor frame consumption and ready/stale state;
- PLY splitting, reassembly, and whole-file resend;
- control sequence rejection, enable requirement, and 500 ms watchdog;
- safe stop and acknowledgement on disabled command and disconnect;
- basic client descriptor matching;
- root Compose startup smoke test.

Do not build contract-validation suites, cross-language golden schemas, lease
tests, security suites, or exhaustive recovery tests before those features
exist.

## Manual Acceptance

1. Initialize submodules, set `VIDEO_FILE` and `SPLAT_FILE`, and start the root
   Compose application.
2. Open the client in the Windows PCVR browser and enter WebXR.
3. Select the recorded driver and raw view; confirm direct live video.
4. Return to setup, select the recorded driver and mock processor, and confirm
   the processor logs incoming frames.
5. Confirm the mounted PLY appears through Spark.
6. Move the headset/controllers and confirm accepted poses appear in driver
   logs.
7. Enable control, then stop; confirm the driver acknowledges
   `safe_stop`.
8. Enable again and close or interrupt the client connection; confirm the
   driver's 500 ms watchdog performs `safe_stop`.
9. Trigger a whole-scene resend and confirm the PLY appears again.

## Completion Criteria

The first version is complete when:

- the three components run through root Compose;
- raw and processed paths both use direct WebRTC connections;
- no central service relays live data;
- the client can render direct video and one processor-provided PLY;
- the processor proves it consumes direct driver video;
- operator poses reach the recorded driver;
- missing enabled control updates reliably trigger `safe_stop`;
- the manual PCVR workflow works over the measured Windows/WSL path;
- the implementation remains small enough to change after what we learn.

Everything else waits for evidence that it is needed.
