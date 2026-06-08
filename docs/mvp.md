# Ito MVP Implementation Plan

## Summary

Create the smallest complete Ito vertical slice:

- A vanilla-JavaScript Three.js/Spark WebXR client.
- A mock robot driver that loops a mounted video file and logs received
  headset/controller poses.
- A mock mono processor that genuinely subscribes to the driver video, consumes
  frames without processing them, and streams a mounted PLY splat scene.
- Real REST, session, capability, Protobuf, and direct WebRTC interfaces that
  future implementations can retain unchanged.

The required target is PCVR on Windows through Virtual Desktop, using a
standalone headset as the PCVR headset. Docker Engine, Docker Compose, the
repository, and development commands run inside WSL2.
Raw video client rendering, real reconstruction, real robots, discovery, direct
Pico-browser access, LAN access, TLS, STUN, and TURN are out of scope.

## Repository Structure

Remove the obsolete `server` submodule and `.gitmodules` entry after preserving
its uncommitted local diff for reference.

```text
client/
  src/
  Dockerfile
  nginx.conf.template
drivers/
  mock/
    app/
    Dockerfile
    pyproject.toml
processors/
  mock/
    app/
    Dockerfile
    pyproject.toml
packages/
  python/ito_service/
protocol/
  openapi.yaml
  ito.proto
  generate.sh
docs/
  mvp.md
compose.yaml
.env.example
```

- Each client, driver, and processor remains an independently buildable
  container.
- Use root Docker Compose with Linux host networking for all MVP containers.
  Because Docker Engine runs inside WSL, containers share the WSL network
  namespace. This makes Nginx's `127.0.0.1` upstreams valid and avoids an extra
  Docker bridge/NAT layer for WebRTC.
- Bind-mount user-supplied assets:
  - `VIDEO_FILE` to `/assets/camera.mp4`
  - `SPLAT_FILE` to `/assets/scene.ply`
- Nginx serves the built client at `http://localhost:8080`.
- Nginx proxies REST and WebRTC signaling only:
  - `/api/drivers/mock/` to `127.0.0.1:8001`
  - `/api/processors/mock/` to `127.0.0.1:8002`
- RTP and DataChannel traffic travels directly between WebRTC peers.

## Technologies

- Client: vanilla JavaScript, Vite, Three.js, `@sparkjsdev/spark`, Protobuf.js.
- Services: Python 3.12, FastAPI, Pydantic, aiortc, PyAV, protobuf.
- Static hosting/control proxy: Nginx.
- REST contract: `protocol/openapi.yaml`.
- WebRTC message contract: `protocol/ito.proto`.
- Generate JavaScript and Python Protobuf bindings during builds.
- Pin dependency versions in lockfiles.

## REST Interface

Every service implements:

```text
GET    /healthz
GET    /.well-known/ito-service
GET    /v1/capabilities
POST   /v1/sessions
GET    /v1/sessions/{session_id}
POST   /v1/sessions/{session_id}/renew
DELETE /v1/sessions/{session_id}
POST   /v1/sessions/{session_id}/webrtc
```

The mock driver additionally exposes the `VideoSource.subscribe_url` endpoint
used by the processor to submit a WebRTC offer.

Rules:

- Browser-facing URLs returned by services are relative to the configured
  service base URL.
- Processor-facing `VideoSource.subscribe_url` is an absolute internal URL.
- Browser-to-service signaling uses one-shot SDP exchange after ICE gathering
  completes.
- Processor-to-driver signaling uses the same offer/answer schema.
- Trickle ICE is not implemented; capabilities explicitly advertise this.
- Sessions expire after 30 seconds and are renewed every 10 seconds.
- Nginx injects a static development bearer token into browser REST requests.
- `VideoSource` uses a random, opaque, one-use token that expires after 60
  seconds and records its intended processor service ID.

## WebRTC Protocol

Use Protobuf messages wrapped in a common envelope containing:

```text
protocol_version
session_id
sequence
payload
```

Coordinate conventions:

- Right-handed coordinates.
- Meters.
- Positive Y is up.
- Negative Z is forward.
- Quaternion order is `x, y, z, w`.
- A transform describes the child pose in the parent frame.

Driver/client channels:

| Channel | Configuration | Messages |
|---|---|---|
| `control` | unordered, `maxRetransmits=0` | operator poses and enable state |
| `telemetry` | unordered, `maxRetransmits=1` | robot transforms and state |
| `events` | reliable, ordered | ownership, errors, stop acknowledgements |

Processor/client channels:

| Channel | Configuration | Messages |
|---|---|---|
| `scene` | reliable, unordered | scene chunk fragments |
| `tracking` | unordered, `maxRetransmits=1` | tracking and camera transforms |
| `events` | reliable, ordered | manifest, acknowledgements, resync, errors |

Required Protobuf payloads:

- `TrackedPose`, `OperatorPoseFrame`, `Transform`, `TelemetryFrame`
- `ServiceEvent`, `TrackingUpdate`
- `SceneManifest`, `SceneChunkFragment`, `SceneChunkAck`, `ResyncRequest`

`OperatorPoseFrame` contains required head pose and optional left/right
controller poses.

Scene chunks use stable IDs and versions. Fragment payloads are at most 48 KiB
and include map epoch, chunk ID, version, fragment index/count, PLY format, total
size, and SHA-256. The client reassembles and verifies the chunk before rendering
it.

## Mock Robot Driver

- Probe and loop the mounted seekable video using `MediaPlayer(..., loop=True)`.
- Advertise one calibrated mono profile using negotiated VP8 WebRTC output.
- Derive width, height, and frame rate from the file.
- Publish deterministic mock pinhole calibration.
- Issue a destination-bound `VideoSource` when the client creates a session.
- Answer the processor's recv-only WebRTC offer with the video track.
- Use `MediaRelay` so the interface supports multiple future subscribers.
- Accept client control/events/telemetry channels.
- Publish fixed mock transforms at 10 Hz:
  - `robot_base -> robot_head`
  - `robot_head -> camera_left`
- Receive operator poses at 30 Hz and log structured pose information to stdout.
- Implement a 500 ms enabled-command watchdog.
- On timeout, disabled command, disconnect, or session expiry, log `safe_stop`
  and emit a stop acknowledgement.

## Mock Mono Processor

- Advertise acceptance of calibrated mono VP8/H264 input and Gaussian PLY
  output.
- On session creation, use the supplied `VideoSource` token to establish a direct
  recv-only WebRTC connection to the driver.
- Continuously call `recv()` on the incoming video track and count frames.
- Ignore frame pixels, but mark the session degraded if input stalls.
- Become ready only after receiving the first video frame.
- Read the mounted PLY once at startup, validate it exists, and compute its
  SHA-256.
- Publish:
  - one map epoch;
  - one scene manifest;
  - one versioned scene chunk containing the fragmented PLY;
  - fixed `map -> camera_left` tracking updates at 10 Hz.
- Place the chunk two meters in front of the initial camera.
- Replay the manifest and chunk when the client sends `ResyncRequest`.

## Client

- Build a real WebXR client with no framework, A-Frame, or TypeScript.
- Display the browser-required minimal `Enter Ito` button immediately.
- Fetch hardcoded service capabilities concurrently while waiting for the user
  gesture.
- Once inside WebXR:
  - show reachable robot drivers as blocks;
  - select blocks through controller-tip collision;
  - show compatible processor blocks after driver selection;
  - support one mock driver and processor while keeping rendering data-driven.
- Use controller grip positions with a small visible touch sphere and contact
  debounce.
- Hide or disable unhealthy/incompatible blocks with CanvasTexture status
  labels.
- Create the driver session, pass its `VideoSource` to the processor, then
  connect directly to both services.
- Send headset plus available left/right controller poses at 30 Hz.
- Show immersive Enable and Stop blocks.
- Stop sending enabled commands on XR exit, service failure, or tracking
  failure.
- Reassemble and verify scene fragments.
- Render the PLY using
  `new SplatMesh({ fileBytes, fileName: "scene.ply" })`.
- Replace chunks by stable ID/version and send acknowledgements.
- Display basic driver, processor, input-frame, tracking, scene, and control
  status.

Raw-video rendering is intentionally excluded from this MVP.

## Test Plan

Automated tests:

- Validate service responses against `openapi.yaml`.
- Cross-language Protobuf golden-message tests between Python and JavaScript.
- Capability compatibility tests.
- Session create, renew, expiry, deletion, and invalid-state tests.
- `VideoSource` expiry, one-use, and destination-ID tests.
- Driver video subscription integration test proving frames are delivered.
- Processor integration test proving it receives and consumes frames.
- Scene fragmentation, out-of-order reassembly, SHA-256, version replacement,
  acknowledgement, and resync tests.
- Control sequence rejection and 500 ms watchdog tests.
- Docker Compose health and endpoint smoke tests.

Manual PCVR acceptance:

1. Set `VIDEO_FILE` and `SPLAT_FILE`, then run `docker compose up --build`.
2. On Windows, start Virtual Desktop and its PCVR runtime, then open
   `http://localhost:8080` in the PCVR-capable Windows browser.
3. Select `Enter Ito` and enter the immersive WebXR session through Virtual
   Desktop.
4. Tap the mock robot-driver block.
5. Tap the mock mono-processor block.
6. Confirm the processor reports received video frames.
7. Confirm the mounted PLY appears through Spark.
8. Move the headset and controllers; confirm poses appear in mock-driver logs.
9. Enable, stop, and exit WebXR; confirm stop acknowledgements and `safe_stop`.
10. Trigger a scene resync and confirm the PLY is restored.

## Assumptions

- Windows 11 workstation with Virtual Desktop, a standalone headset, and a
  PCVR-capable Windows Chromium browser.
- Docker Engine and the Docker Compose plugin run directly inside WSL2;
  development files live in the WSL filesystem. Docker Desktop is not required.
- The Windows browser uses `http://localhost:8080`; browsers treat localhost as a
  WebXR secure context.
- The first implementation task is a networking spike proving that the Windows
  browser can establish direct WebRTC connections to both aiortc service
  containers. Inspect the resulting ICE candidates and connection path between
  Windows and WSL; do not assume WSL localhost forwarding also handles WebRTC.
- No TLS, CORS, STUN, TURN, LAN headset, or public hosting support in this MVP.
- The mounted video contains one seekable video stream.
- The mounted PLY is Spark-compatible, centered near its origin, and small enough
  for interactive loading.
- The mock processor proves the permanent processor interface but performs no
  reconstruction.
- Development bearer authentication is not production security; the REST and
  capability-token interfaces remain stable when real authentication is added.
