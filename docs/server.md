# Ito Server

The Ito server is a Python application plus a selected robot-driver container.
Together they turn a robot's camera stream into a live 3D scene for a WebXR
client and turn the operator's tracked pose into safe robot commands.

The server runs on a GPU-equipped computer near the operator. The core
application is deliberately independent of ROS2, vendor SDKs, and any particular
reconstruction algorithm. Robot drivers run as separate containers, while
reconstruction backends and client transports meet through small, typed
interfaces so each can be replaced independently.

## Goals

- Accept mono, stereo, and eventually RGB-D video from different robot families.
- Build a continuously updated 3D Gaussian scene while estimating the pose of
  each camera frame.
- Let a browser render the latest scene at the headset's refresh rate without
  waiting for new camera frames.
- Stream robot and tracking metadata in the same coordinate system as the scene.
- Forward operator pose to the robot through validation, limits, and a watchdog.
- Record enough input and output data to reproduce failures offline.

This is a latency-compensation system, not a latency-elimination system. The
client can move its virtual viewpoint inside the reconstructed scene while a new
robot image is in flight, but unseen or newly revealed surfaces cannot be
invented reliably.

## System Boundaries

```text
 Robot
   camera stream + calibration + telemetry
                    |
                    v
        RobotDriver container
                    |
       shared memory + local IPC
                    |
                    v
       Ito core + ReconstructionBackend
                    |
        SceneUpdate + TrackingState
                    |
                    v
 WebRTC session <-> WebXR / Three.js client
                    |
           OperatorPoseCommand
                    |
                    v
        SafetyController -> RobotDriver -> Robot
```

The server owns:

- frame ingestion, synchronization, and backpressure;
- reconstruction lifecycle and tracking-health reporting;
- the canonical scene and coordinate-frame tree;
- client sessions, authentication, and scene synchronization;
- validation and expiry of operator commands;
- metrics, logs, and recordings.

The robot driver container owns robot-specific protocols, dependencies, and
conversions. The WebXR client owns rendering and headset/controller sampling.
Neither is allowed to depend on the internals of a reconstruction backend.

## Coordinate Frames

All poses are rigid transforms with an explicit parent frame, child frame,
timestamp, and clock domain. The server estimates offsets between robot, server,
and browser clocks and normalizes timestamps to its monotonic clock where
possible. Internally, transforms are represented as translation in meters plus a
normalized quaternion. Matrices are only created at API boundaries.

Required frames:

| Frame | Meaning |
|---|---|
| `map` | Stable reconstruction coordinate system |
| `robot_base` | Robot's physical base or torso reference |
| `camera_left` | Left or mono camera optical frame |
| `camera_right` | Right camera optical frame, when present |
| `robot_head` | Point controlled by the operator's head pose |
| `client_origin` | WebXR reference space at session calibration |
| `client_head` | Current headset pose |

The driver supplies static robot transforms such as
`robot_base -> camera_left` and `robot_head -> camera_left`. The reconstruction
backend estimates `map -> camera_left`. The server can then derive the robot
head/eye positions in `map`.

At the start of teleoperation, the client and server perform an explicit
alignment step that establishes `robot_head -> client_head`. Operator commands
are relative to that alignment, not raw WebXR world coordinates. This prevents a
browser recenter or a new session origin from causing a sudden robot movement.

Mono reconstruction does not provide metric scale by itself. A mono driver must
provide another scale source, such as known camera motion, robot kinematics,
wheel odometry, an IMU, or depth estimates. Until scale is initialized, the
server marks the map as `scale_status=unknown` and does not use reconstructed
translation for robot control.

## Internal Data Contracts

Use immutable dataclasses or Pydantic models at component boundaries. Large
image and tensor payloads stay in NumPy, PyTorch, or shared-memory buffers rather
than being serialized between every stage.

```python
@dataclass(frozen=True)
class CameraCalibration:
    camera_id: str
    width: int
    height: int
    model: Literal["pinhole", "fisheye"]
    intrinsics: tuple[float, ...]
    distortion: tuple[float, ...]
    t_rig_camera: Transform


@dataclass(frozen=True)
class VideoFrame:
    camera_id: str
    sequence: int
    captured_at_ns: int
    capture_clock: str
    received_at_ns: int
    width: int
    height: int
    stride: int
    encoding: str
    data: memoryview


@dataclass(frozen=True)
class FrameSet:
    sequence: int
    frames: tuple[VideoFrame, ...]
    calibration: tuple[CameraCalibration, ...]


@dataclass(frozen=True)
class SceneUpdate:
    map_epoch: UUID
    revision: int
    changed_chunks: tuple[SplatChunk, ...]
    removed_chunk_ids: tuple[UUID, ...]
    transforms: tuple[StampedTransform, ...]
    tracking: TrackingState
```

Every `FrameSet` contains either one mono frame or a synchronized stereo pair.
Stereo drivers must reject or flag pairs whose capture timestamps differ beyond
a configured tolerance. Receive time is useful for network metrics but must not
be mistaken for capture time.

## Robot Driver Containers

Every robot integration is packaged as a separate container. Only the selected
driver container runs for a session. The robot itself does not need Ito-specific
software; a driver connects to interfaces the robot already exposes, such as
ROS2 topics, RTSP, MAVLink, or a vendor SDK.

Ito has one canonical ROS2 driver implementation. It is configured for different
ROS2 robots rather than forked per robot or paired with alternative ROS2 camera
paths. It supports mono, stereo, and RGB-D topics plus calibration, TF, robot
state, and commands.

```text
Robot network
    |
    v
driver container: ROS2 / vendor SDK / protocol dependencies
    |
    +-- Unix socket: capabilities, telemetry, commands, health
    |
    +-- shared-memory ring: mono or synchronized stereo frames
    |
    v
Ito core: reconstruction, client sessions, safety, recording
```

The Ito core can run directly on the host or in its own container. Containers are
a dependency boundary, not the data transport. Camera pixels do not travel over
Docker networking or through JSON, Protobuf, gRPC, or HTTP between the local
driver and the core.

This makes installation a small Docker Compose application while keeping ROS2
and incompatible vendor dependencies out of the core image. Adding a driver
means publishing another driver image, not changing the robot or the Ito core.

### Driver IPC Contract

The local driver contract has two planes:

| Plane | Transport | Contents |
|---|---|---|
| Control | versioned messages over a Unix domain socket | capabilities, calibration, telemetry, health, commands, frame notifications |
| Video | fixed-size ring buffer in a shared tmpfs volume | raw or encoded mono/stereo frame payloads |

The control protocol can use Protobuf over gRPC or a small framed Unix-socket
protocol. On connection, the driver sends `RobotCapabilities`, which declares
available cameras, calibrations, static transforms, source clock domains,
command types, limits, video encodings, and whether timestamps were generated at
capture time. Unsupported capabilities are explicit.

Each shared-memory frame slot contains:

```text
slot state and generation
frameset sequence
capture and receive timestamps
clock domain
camera count
for each camera: width, height, stride, pixel format, payload offset, payload size
left payload
right payload, when present
```

The driver writes a complete mono frame or synchronized stereo pair into one
slot and only then publishes its generation in a Unix-socket notification. The
core leases that slot until reconstruction no longer needs it and returns a
release message. This single-producer/single-consumer ownership protocol keeps
partially written frames invisible without requiring locks around pixel data. If
no slot is available, the driver drops the new frame; it never waits long enough
to build latency.

The ring-buffer layout and control messages form the versioned Ito Driver
Protocol. Small Python and C++ driver SDKs provide its shared-memory writer,
control client, health reporting, and conformance tests so driver authors only
implement robot-specific capture, telemetry, and commands.

### Performance Model

Uncompressed stereo video is large. Two 1456x1088 BGR cameras at 30 fps produce
about 285 MB/s, or 2.28 Gbit/s:

```text
1456 * 1088 * 3 bytes * 2 cameras * 30 fps ~= 285 MB/s
```

That rate is usually too high for WiFi and may exceed a robot's practical
network link before containers become relevant. If a robot does not already
expose raw stereo over a suitable network, Ito must consume an existing
compressed stream, request a lower resolution/frame rate, or require the robot
to provide a better stream. No server-side IPC design removes this robot-to-host
bandwidth constraint.

Serializing that through a socket would add copies, CPU time, allocations, and
latency. With the shared-memory design, the normal local path is:

```text
ROS/vendor frame -> one copy into a shared-memory slot -> reconstruction reads it
```

The core passes a slot descriptor to the reconstruction worker. That worker maps
the same shared-memory volume and creates a memoryview or NumPy view instead of
making another Python-owned image copy. Reconstruction copies or uploads the
frame only when its GPU pipeline requires it. The core releases the slot
immediately after that upload.

Prefer raw frames over local shared memory when the robot already publishes raw
images. If the robot only exposes compressed video, decode once in the driver or
reconstruction worker based on benchmarking. Compressed frames reduce robot
network bandwidth, but decoding can add latency and may reduce SLAM quality.

Keep at most two or three shared-memory slots per camera set. For the example
stereo stream, three raw slots require about 29 MB. The implementation must
measure frame age, slot wait time, dropped frames, copies, decode time, and
host-to-GPU upload time. A driver is acceptable only if the container boundary
adds less than one millisecond at the 95th percentile on the target workstation.

The driver protocol is language-neutral. The canonical ROS2 driver can start
with `rclpy`, but may move its high-rate image subscription and shared-memory
writer to `rclcpp` if benchmarks show callback, allocation, or copy overhead.
That is an internal optimization of the same ROS2 driver, not a second driver
implementation. In most deployments, robot network transport, video decoding,
and reconstruction will cost much more than the container boundary itself.

Commands and telemetry are small, so their Unix-socket overhead is negligible.
The core retains command validation and the watchdog; a driver also implements a
final local command timeout so a crashed core cannot leave the robot moving.

### Canonical ROS2 Driver

The first driver is also Ito's only ROS2 driver. Its image is based on a
supported ROS2 distribution and contains ROS2, the common message packages, and
the Ito Driver SDK. Configuration selects:

- mono, stereo, or RGB-D camera topics;
- matching `CameraInfo` topics;
- image encodings and synchronization tolerance;
- TF frames and robot-state topics;
- command topics, message mappings, limits, and watchdog behavior;
- ROS domain, DDS implementation, discovery peers, and QoS profiles.

The driver subscribes directly to existing image, `CameraInfo`, TF, robot-state,
and command topics. It preserves source timestamps, pairs stereo and RGB-D
frames by capture timestamp, and publishes bounded robot commands. It accepts
standard ROS2 messages by default. Robot-specific message types are supported by
small adapter plugins loaded into this same driver image and protocol, not by
creating another ROS2 driver architecture.

ROS2 remains entirely inside this driver container; the Ito core does not import
`rclpy` or link to ROS2. DDS discovery often works most predictably with host
networking:

```yaml
services:
  ito-server:
    image: ghcr.io/ito/ito-server
    volumes:
      - driver-ipc:/run/ito-driver
      - driver-frames:/run/ito-frames
    depends_on:
      - robot-driver

  robot-driver:
    image: ghcr.io/ito/driver-ros2-jazzy
    network_mode: host
    volumes:
      - driver-ipc:/run/ito-driver
      - driver-frames:/run/ito-frames
    environment:
      ROS_DOMAIN_ID: "0"
      ITO_CONFIG: /config/robot.yaml

volumes:
  driver-ipc:
  driver-frames:
    driver_opts:
      type: tmpfs
      device: tmpfs
```

The exact Compose networking depends on the DDS implementation and robot
network. Host networking is convenient but broadens the driver's network access;
production deployments should document and test a narrower DDS configuration
where possible. Non-ROS drivers can use vendor SDKs, RTSP, WebRTC, MAVLink, or a
custom protocol without changing the rest of the server.

## Reconstruction API

Reconstruction is a backend, not application control flow:

```python
class ReconstructionBackend(Protocol):
    async def start(self, cameras: tuple[CameraCalibration, ...]) -> None: ...
    async def process(self, frames: FrameSet) -> SceneUpdate | None: ...
    async def snapshot(self) -> SceneSnapshot: ...
    async def reset(self, reason: str) -> None: ...
    async def close(self) -> None: ...
```

The backend owns tracking, keyframe selection, loop closure, Gaussian creation,
and map optimization. It reports at least:

- tracking state: `initializing`, `tracking`, `degraded`, or `lost`;
- estimated `map -> camera_left` transform and confidence;
- map epoch and monotonically increasing revision;
- added, replaced, and removed scene chunks;
- scale status and loop-closure/map-reset events.

The server should first integrate a complete online Gaussian-SLAM implementation
behind this API instead of attempting to combine unrelated tracking and mapping
projects prematurely. Candidate backends must be evaluated with Ito's live
streams for latency, relocalization, dynamic objects, memory growth, license,
and whether map updates can be exported during operation.

The processing path inside a backend is:

```text
decode -> validate calibration -> undistort/rectify -> track camera
       -> select keyframe -> update Gaussian map -> export changed chunks
```

Tracking runs for every accepted frame. Expensive map optimization and chunk
export run at their own lower rates. This keeps camera-pose metadata fresh even
when the visible Gaussian map changes only a few times per second.

The reconstruction worker runs in its own process with exclusive ownership of
its CUDA context. Frame ingestion uses a small bounded queue, normally one or two
`FrameSet` objects. When reconstruction falls behind, the server drops old
unprocessed frames and keeps the newest one. It never builds an ever-growing
latency queue.

### Practical Development Backend

The application should also include a `RecordedSceneBackend` that replays a
known splat scene, camera trajectory, and tracking state. It lets the transport,
WebXR renderer, metadata, reconnect behavior, and pose-control path be developed
and tested before live Gaussian reconstruction is dependable.

## Scene Model

The scene is divided into independently replaceable chunks, normally by
keyframe or spatial region. A chunk has:

- a stable UUID and monotonically increasing version;
- a transform from chunk-local coordinates to `map`;
- packed RGB Gaussian splats;
- an axis-aligned bounding box and optional level-of-detail variants.

Chunk replacement is preferable to mutating global splat indices. It gives the
backend freedom to re-optimize a region, lets the client update one
`SplatMesh`, and makes packet loss or reconnect recovery local.

For the browser representation, use Spark's 16-byte packed RGB splat layout when
its quantization is visually acceptable. The server retains a higher-precision
internal representation and performs chunk-local quantization before streaming.
Spherical harmonics can be added later as an optional capability; RGB-only is a
bandwidth choice, not a reconstruction invariant.

Loop closure may move or replace existing chunks. A major reset creates a new
`map_epoch`; clients discard all chunks from the previous epoch.

## Client Transport

Use an HTTPS endpoint for authentication, session creation, and WebRTC
signaling. WebRTC connectivity still requires configured STUN and, for networks
that cannot connect directly, TURN.

Each client session has separate DataChannels with different delivery policies:

| Channel | Delivery | Contents |
|---|---|---|
| `scene` | reliable, ordered | chunk snapshots/replacements, removals, map resets |
| `telemetry` | unordered, limited retransmission | transforms, tracking health, robot state |
| `control` | unordered, no retransmission | timestamped operator pose commands |
| `events` | reliable, ordered | calibration, errors, stop/enable acknowledgements |

Scene updates are reliable because dropping a chunk replacement would leave the
client with a permanently inconsistent map. Telemetry and control favor the
newest value because stale poses have no value.

Use a compact versioned binary envelope, implemented with Protobuf, FlatBuffers,
or another generated schema:

```text
protocol_version
session_id
message_type
map_epoch
revision
sequence
sent_at_ns
payload_length
payload
```

Large chunks are split into numbered fragments and reassembled before becoming
visible. The client acknowledges the highest applied scene revision. On connect,
reconnect, revision gap, or explicit resync request, the server sends a manifest
followed by the required chunk snapshots. Server-side per-client queues have
byte limits; a slow client is resynchronized or disconnected instead of
consuming unbounded memory.

The server publishes transforms and metadata separately from splat chunks, at a
higher rate. This includes at least the robot head and eye poses, current camera
pose, tracking health, scale status, round-trip latency, and map revision.

## Pose Control and Safety

Client pose is an input request, never a command that is forwarded verbatim.
The control path is:

```text
WebXR sample
 -> authenticate session
 -> reject old/out-of-order samples
 -> transform relative to session alignment
 -> clamp workspace, velocity, and acceleration
 -> map to robot-supported command
 -> send through driver
```

Each command includes a sequence number and a client monotonic timestamp. The
server estimates clock offset and rejects stale commands. A dead-man/enable
state is required before motion. If control messages stop, tracking becomes
invalid, the client disconnects, or the driver errors, a watchdog sends the
robot's configured safe-stop command.

Robot-specific limits come from the driver and cannot be overridden by the
browser. Control and scene viewing permissions are separate so spectators can
connect without being able to move the robot. Only one session owns control
unless a robot explicitly supports another policy.

## Python Package Layout

```text
server/
  ito_server/
    app.py                 # configuration and lifecycle
    models.py              # shared typed contracts
    frames.py              # frame queues and synchronization
    transforms.py          # frame tree and coordinate conversions
    drivers/
      client.py            # driver control socket client
      protocol.py          # generated control messages
      shared_frames.py     # shared-memory frame reader
    reconstruction/
      base.py
      recorded_scene.py
      gaussian_slam.py
    scene/
      store.py             # canonical chunk store and revisions
      packing.py           # browser/Spark packing
    transport/
      signaling.py         # HTTPS auth and WebRTC offer/answer
      peer.py              # DataChannels and per-client queues
      protocol.py          # generated binary messages
    control/
      safety.py
      mapping.py
    recording.py
    metrics.py
  tests/
drivers/
  sdk/
    python/                # Python control client and shared-memory writer
    cpp/                   # C++ control client and shared-memory writer
    conformance/           # tests every driver image must pass
  ros2-jazzy/
    Dockerfile
    adapters/              # optional robot-specific message mappings
```

Recommended runtime choices:

| Concern | Initial choice |
|---|---|
| Python | Python 3.12 |
| Configuration/models | Pydantic Settings and dataclasses |
| HTTP/signaling | FastAPI with an ASGI server |
| WebRTC | `aiortc` |
| Numeric/GPU data | NumPy and PyTorch |
| Wire schema | Protobuf |
| Deployment | Docker Compose with one selected driver image |
| Metrics | Prometheus client |
| Tests | pytest, pytest-asyncio, and recorded sessions |

`asyncio` coordinates network I/O and lifecycle, but CPU-heavy decoding and
GPU-heavy reconstruction do not run on the event-loop thread. Use structured
task groups so a failed component is restarted or shuts the session down
deliberately.

Configuration is validated at startup and includes the selected driver,
calibration files, reconstruction backend, network endpoints, credentials,
STUN/TURN servers, queue sizes, and robot safety limits. Secrets come from the
environment or a secret store, not checked-in YAML.

Driver images are versioned independently but declare the Ito Driver Protocol
versions they support. The server refuses an incompatible driver before enabling
control.

## Observability and Recording

Expose structured logs and metrics for:

- capture-to-server, reconstruction, and server-to-client latency;
- input, processed, and dropped frame rates;
- tracking state and relocalization count;
- splat/chunk counts, map bytes, and GPU memory;
- scene revisions sent, acknowledged, and resynchronized;
- client round-trip time and DataChannel buffered bytes;
- command age, clamp events, watchdog stops, and driver errors.

An optional session recorder writes calibration, compressed input frames,
timestamps, robot state, operator commands, tracking results, and scene updates.
The same recording is consumable by test drivers and reconstruction benchmarks.
This makes regressions reproducible without requiring a live robot.

## Failure Behavior

| Failure | Server behavior |
|---|---|
| Camera stalls | Mark tracking degraded, stop feeding reconstruction, keep rendering the last map |
| Tracking lost | Publish lost state, freeze map updates, stop translation control if it depends on map scale |
| Reconstruction crashes | Keep control and client session safe, restart worker, begin a new map epoch |
| Client misses scene data | Send manifest and required chunk snapshots |
| Client is too slow | Drop telemetry first, then resync or disconnect the client |
| Control stream stops | Trigger robot watchdog and safe stop |
| Driver disconnects | Trigger safe stop, retain the map, reconnect with backoff |

## Implementation Sequence

### Milestone 1: End-to-End Skeleton

- Implement the typed contracts, lifecycle, and configuration.
- Implement the Ito Driver Protocol, driver SDKs, and conformance tests.
- Package the canonical ROS2 driver container with mono and stereo image,
  `CameraInfo`, TF, robot-state, and command topic support.
- Configure the first robot entirely through topic, frame, QoS, and command
  mappings.
- Preserve capture timestamps and validate synchronized stereo pairs.
- Verify DDS discovery from the driver container without installing anything new
  on the robot.
- Prove the shared-memory frame path under sustained load.
- Implement `RecordedSceneBackend`.
- Serve HTTPS signaling and one authenticated WebRTC client.
- Stream a recorded chunked splat scene plus live camera/head metadata.
- Receive headset poses and log the validated, clamped command without moving a
  robot.

### Milestone 2: Safe Robot Control

- Add the first robot's command adapter, limits, calibration flow, enable state,
  and watchdog.
- Record and replay complete sessions.
- Add integration tests for disconnects, stale commands, and browser recentering.

### Milestone 3: Live Mono Reconstruction

- Integrate one complete online mono Gaussian-SLAM backend in an isolated worker.
- Export chunk snapshots and map epochs through the reconstruction API.
- Measure motion-to-photon behavior, map quality, memory growth, and recovery on
  recorded and live robot sequences.
- Add a metric scale source before enabling translational teleoperation.

### Milestone 4: Stereo Reconstruction and Driver Hardening

- Add a stereo reconstruction backend and metric-scale validation.
- Benchmark `rclpy`; move the image hot path to `rclcpp` inside the same driver
  only if measurements require it.
- Add any required robot-specific message adapter plugins without forking the
  ROS2 driver protocol or architecture.
- Test supported DDS and robot-network configurations.

## Acceptance Criteria

The first useful version is complete when:

- changing robot drivers does not change reconstruction or transport code;
- the Ito core runs without ROS2 or robot-vendor SDKs installed;
- all ROS2 robots use the same configurable ROS2 driver implementation;
- driver containers pass protocol conformance and sustained-throughput tests;
- the measured driver-container boundary adds less than one millisecond p95;
- changing reconstruction backends does not change robot or client code;
- a reconnecting browser deterministically reaches the current scene revision;
- all transmitted poses name their coordinate frames and timestamps;
- frame overload drops work instead of increasing latency without bound;
- stale or absent control input always produces a tested safe stop;
- a recorded session can reproduce the server's scene and control behavior;
- latency, tracking health, map size, and command age are observable.

## Relevant Projects

- [aiortc](https://github.com/aiortc/aiortc) for Python WebRTC.
- [Spark](https://github.com/sparkjsdev/spark) for Three.js/WebXR Gaussian
  rendering and its compact packed-splat representation.
- [gsplat](https://github.com/nerfstudio-project/gsplat) as a Python/CUDA
  Gaussian-splatting toolkit, not by itself a complete online SLAM system.
- [ORB-SLAM3](https://github.com/UZ-SLAMLab/ORB_SLAM3) as a reference for robust
  mono/stereo/RGB-D tracking; its GPLv3 license and C++ integration requirements
  must be considered before adoption.
