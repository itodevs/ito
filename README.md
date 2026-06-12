# Ito
Immersive Teleoperation: pilot any robot with any VR gear

# Ito Services

Ito is led by the WebXR client. Everything outside the client is a service that
advertises capabilities, accepts a session configuration, and then communicates
directly with the service or client that needs its data.

There is no central Ito server and no Ito application service that merely
forwards pose, video, or scene data between otherwise connected components.

Ito defines two service types:

1. **Robot drivers** expose a robot's cameras, calibration, transforms,
   telemetry, and controls.
2. **Visual processors** consume a compatible robot video stream and produce a
   representation the client can render.

The client enters WebXR, connects to a hardcoded list of services, presents them
as interactive blocks, starts the selected sessions, and owns the resulting
session graph.

## Why This Shape

```text
                         REST setup
                  +----------------------+
                  |     WebXR client     |
                  +----------------------+
                    |                  ^
       pose/control |                  | splats
                    v                  | tracking metadata
             +-------------+     +------------------+
             | robot driver|---->| visual processor |
             +-------------+     +------------------+
                    | direct video stream
                    |
                    +-- telemetry/raw video --> client
```

Live data follows the shortest useful path:

- robot video flows directly from the robot driver to the visual processor;
- processed visuals flow directly from the visual processor to the client;
- raw video viewing flows directly from the robot driver to the client;
- operator poses flow directly from the client to the robot driver;
- robot telemetry flows directly from the robot driver to the client.

REST is only the control plane: identity, capability inspection, session setup,
status, and teardown. It is never used for live frames, splats, poses, or
telemetry.

This removes a central bottleneck and makes every processor and driver
independently replaceable. It also moves responsibilities that previously
belonged to a central server:

- the client owns service selection, session orchestration, and coordinate-frame
  composition;
- the robot driver owns command validation, limits, and the safety watchdog;
- the visual processor owns reconstruction state, scene recovery, and output
  backpressure.

This is a good architecture for Ito, but it does not remove complexity; it moves
complexity into the client and the service contracts. The client must coordinate
multiple authenticated sessions, present partial failures clearly, and clean up
leases. Services need trusted HTTPS, compatible protocol versions, and direct
network reachability. These costs are preferable to putting a forwarding server
in every live-data path.

Services are deployed before the client connects to them. For the first version,
their URLs are hardcoded in the client configuration. Dynamic configuration,
discovery, and launching containers from the browser are deliberately deferred.

## One Important Exception

A separate raw-video passthrough processor would add a forwarding hop while doing
no useful processing. That conflicts with the direct-data principle and adds
latency. Raw mono or stereo viewing is therefore a client rendering mode: the
client subscribes directly to a browser-compatible video profile from the robot
driver.

Actual visual processors share the same API and session lifecycle:

| Implementation | Accepted input | Output |
|---|---|---|
| Mono Gaussian processor | calibrated mono | Gaussian splats |
| Stereo Gaussian processor | calibrated synchronized stereo | Gaussian splats |
| RGB-D Gaussian processor | calibrated synchronized RGB-D | Gaussian splats |

The immersive setup scene presents raw direct viewing alongside compatible
processors, but no raw-passthrough service is started.

## Common Service API

Every service exposes an HTTPS REST API using the same versioning,
authentication, error, and session conventions.

```text
GET    /.well-known/ito-service
GET    /v1/capabilities
POST   /v1/sessions
GET    /v1/sessions/{session_id}
DELETE /v1/sessions/{session_id}
POST   /v1/sessions/{session_id}/webrtc
```

`/.well-known/ito-service` returns the small identity document used when the
client contacts a hardcoded service endpoint:

```json
{
  "protocol": "ito-service",
  "protocol_version": "1.0",
  "service_id": "c50a51ac-58c6-42a7-9f35-3d68916e4e10",
  "service_type": "robot-driver",
  "name": "Workshop ROS2 Robot",
  "capabilities_url": "/v1/capabilities"
}
```

`POST /v1/sessions` validates a requested configuration and allocates runtime
resources. Starting a session does not start a container; services are already
running programs or containers. It starts one logical connection and processing
session inside that service.

REST responses include explicit protocol versions and stable machine-readable
error codes. Services reject unsupported configurations instead of silently
degrading them.

## Initial Service List

The first version does not implement service discovery or user-editable service
configuration. Robot-driver and visual-processor URLs are hardcoded in the
client's deployment configuration.

The client enters WebXR as soon as possible, fetches identity and capabilities
from that list, and represents each reachable service as a physical block in the
immersive setup scene. Dynamic configuration and automatic discovery can be
designed later without changing session or live-data protocols.

All browser-facing REST and WebRTC signaling endpoints require trusted HTTPS,
appropriate CORS policy, and authentication. Local deployments need a deliberate
certificate strategy; self-signed endpoints that the browser refuses are not
usable service endpoints.

## Capabilities and Compatibility

The client selects a robot driver first. It then compares the driver's offered
video profiles against each processor's accepted input profiles.

A video profile describes the data rather than the implementation that produced
it:

```json
{
  "profile_id": "stereo-front-low-latency",
  "kind": "stereo",
  "cameras": ["camera_left", "camera_right"],
  "width": 1456,
  "height": 1088,
  "frame_rate": 30,
  "synchronized": true,
  "timestamp_source": "capture",
  "clock_domain": "robot-monotonic",
  "metric_scale": true,
  "calibration": true,
  "transport": "webrtc-rtp-v1",
  "encoding": "h264",
  "codec_profile": "constrained-baseline"
}
```

Processor capabilities contain input constraints and output representations:

```json
{
  "service_type": "visual-processor",
  "accepts": [
    {
      "kind": "stereo",
      "requires": {
        "synchronized": true,
        "calibration": true,
        "timestamp_source": "capture"
      },
      "transport": "webrtc-rtp-v1",
      "encodings": ["h264", "vp9"]
    }
  ],
  "outputs": [
    {
      "representation": "gaussian-splats",
      "protocol": "ito-scene-v1"
    }
  ]
}
```

Compatibility is the intersection of media kind, geometry, encoding, timing,
calibration, scale requirements, and WebRTC codec support. The client can show
why a processor is incompatible, such as "requires synchronized stereo" or "no
common codec." It also shows a raw direct-view option when the driver offers a
browser-compatible WebRTC profile.

## Robot Driver Service

A robot driver adapts one robot protocol to Ito. Drivers may use ROS2, a vendor
SDK, RTSP, MAVLink, or another native robot interface. The robot does not need to
run Ito-specific software when its existing interfaces provide the required
data.

The canonical ROS2 driver is one configurable container supporting mono, stereo,
RGB-D, `CameraInfo`, TF, robot state, and command topics. Robot-specific ROS2
message adapters are plugins within that driver, not separate ROS2
architectures.

### Robot Driver Outputs

The driver offers:

- one or more versioned video profiles;
- camera calibration and static transforms;
- timestamp and synchronization quality;
- robot telemetry and current transforms;
- a read-only video subscription capability for a processor or client.

For WebRTC transport, video uses RTP media tracks wherever a suitable codec
exists. Calibration, frame-set IDs, exact capture timestamps, transforms, and
telemetry use DataChannels. Stereo tracks share a clock and every pair carries a
common frame-set ID.

RGB-D may use an RTP color track plus a depth payload stream because ordinary
browser video codecs do not preserve depth data. Its exact encoding is declared
by the profile.

### Robot Driver Inputs

The client opens a separate direct WebRTC connection to the driver:

| Channel | Delivery | Contents |
|---|---|---|
| `control` | unordered, no retransmission | newest operator pose and enable state |
| `telemetry` | unordered, limited retransmission | robot transforms and state |
| `events` | reliable, ordered | calibration, ownership, errors, stop acknowledgements |

The driver never forwards client poses verbatim. It:

1. authenticates the controlling client;
2. rejects stale and out-of-order samples;
3. applies the session alignment transform;
4. clamps workspace, velocity, acceleration, and robot-specific limits;
5. converts the pose to the robot's native command;
6. stops the robot when the control watchdog expires.

Viewing and control permissions are separate. A driver grants control ownership
to at most one client unless the robot explicitly supports another policy. The
driver owns the final watchdog because there is no safer intermediary to do it.

### Robot Driver Session Result

When the client creates a driver session, the response contains:

- a client control/telemetry WebRTC signaling endpoint;
- the selected robot video profile;
- an expiring, read-only `VideoSource` descriptor for a processor or raw-view
  client;
- coordinate-frame and calibration metadata;
- session expiry and teardown information.

The `VideoSource` descriptor is a capability token, not raw credentials. It only
allows its named destination to subscribe to the selected video stream and
cannot control the robot.

## Visual Processor Service

A visual processor consumes one `VideoSource` and publishes one renderable
output. It never receives operator poses and never sends robot commands.

The client starts it with the source descriptor returned by the driver:

```json
{
  "source": {
    "service_id": "driver-service-id",
    "profile_id": "stereo-front-low-latency",
    "subscribe_url": "https://driver.example/v1/video-subscriptions",
    "token": "short-lived-read-only-token"
  },
  "requested_output": {
    "representation": "gaussian-splats",
    "quality": "interactive"
  }
}
```

The processor contacts the driver directly, negotiates the WebRTC session and
codec, and reports whether the session is initializing, ready, degraded, or
failed. The client does not relay SDP, video, or processor output.

### Processor Input Transport

WebRTC provides congestion control, NAT traversal mechanisms, timestamps, and
hardware codec integration. It still requires direct signaling plus configured
STUN and sometimes TURN. TURN is a relay of last resort and adds latency, but is
necessary on networks where a direct path cannot be established.

WebRTC is the only initial processor-input transport, including when the driver
and processor run on the same host. This keeps the first protocol and
implementation small and exercises the same path in development and deployment.

### Processor Behavior

Reconstruction processors own:

- decode, calibration validation, undistortion, and rectification;
- tracking, keyframe selection, loop closure, and map optimization;
- bounded input queues and frame dropping;
- scene chunking, revisions, snapshots, and reconnect recovery;
- tracking health, scale status, and map-reset events.

Tracking runs for every accepted frame when possible. Expensive map optimization
and scene export run independently at lower rates. Input queues remain small,
normally one or two frame sets. When overloaded, the processor drops old work
instead of accumulating latency.

Mono processors report `scale_status=unknown` until they have a metric scale
source. Stereo and RGB-D processors validate scale rather than assuming it.

## Processor-to-Client Output

The client opens a direct WebRTC connection to the processor. For Gaussian
processors, separate DataChannels use delivery policies appropriate to the data:

| Channel | Delivery | Contents |
|---|---|---|
| `scene` | reliable, unordered | versioned chunk snapshots/replacements, removals, map resets |
| `tracking` | unordered, limited retransmission | camera pose, tracking health, scale status |
| `events` | reliable, ordered | session state, errors, resync acknowledgements |

Scene changes are reliable because losing a replacement would leave the client
with a permanently inconsistent map. They are unordered to avoid one delayed
chunk blocking newer independent chunks. Chunk IDs and versions make ordering
unnecessary; the client ignores superseded versions. Tracking data favors the
newest value.

The Gaussian scene is divided into independently replaceable chunks. Each chunk
has a stable ID, version, transform into `map`, packed splats, bounds, and
optional LOD variants. The client acknowledges applied scene revisions. On
connect, reconnect, revision gap, or explicit resync, the processor sends a
manifest followed by the required chunk snapshots.

The initial browser representation uses compact RGB splats compatible with
Spark. Spherical harmonics are an optional negotiated capability, not an
assumption.

Large scene messages are fragmented below the negotiated DataChannel message
limit and reassembled by chunk ID and version.

For raw viewing, this processor connection does not exist. The client subscribes
directly to the driver's RTP video tracks plus calibration and frame metadata.

## Coordinate Frames

Every transform names its parent frame, child frame, timestamp, and clock domain.
Translations use meters and rotations use normalized quaternions.

Required common frames are:

| Frame | Owner |
|---|---|
| `robot_base` | robot driver |
| `robot_head` | robot driver |
| `robot_eye_left` | robot driver when available |
| `robot_eye_right` | robot driver when available |
| `camera_left` | robot driver |
| `camera_right` | robot driver when present |
| `map` | reconstruction processor |
| `client_origin` | client |
| `client_head` | client |

The driver supplies robot-to-camera transforms. The processor publishes
`map -> camera_left`. The client composes these transforms to place robot
metadata, including the current robot head and eye positions, in the
reconstructed scene. Frame IDs are stable across driver and processor streams.

At the start of control, the client and driver perform an explicit alignment.
Commands are relative to that alignment, never raw WebXR world coordinates.
Browser recentering therefore cannot cause a sudden robot movement.

Services expose clock-sync quality. The client estimates offsets among its own,
driver, and processor clocks for latency display and stale-data detection.
Capture timestamps remain attached to frames through the entire pipeline.

## Low-Latency Rules

1. Live data never travels through REST.
2. The client connects directly to the driver and processor.
3. The processor connects directly to the driver.
4. WebRTC uses direct ICE candidates when possible; TURN is fallback only.
5. Video profiles avoid B-frames and deep receiver jitter buffers.
6. Every queue is byte- or frame-bounded and drops stale work under pressure.
7. Control and tracking channels are unordered and do not retransmit stale data.
8. Persistent scene state uses reliable delivery and explicit resynchronization.
9. Encode, decode, copy, queue, network, reconstruction, and render delays are
    measured separately.

Raw stereo is expensive. Two 1456x1088 RGB cameras at 30 fps produce about
285 MB/s, or 2.28 Gbit/s, before protocol overhead. No service architecture
removes that robot-to-processor bandwidth requirement. The selected profile may
need compression, lower resolution, lower frame rate, a wired network, or a
processor co-located with the driver.

After the WebRTC implementation is measured, a future shared-memory transport
may be considered for co-located driver and processor containers if WebRTC
encoding, decoding, or copying is a demonstrated bottleneck. It should remain an
optional optimization behind the same video-profile semantics, not part of the
initial protocol.

## Session Setup

The client performs setup inside WebXR:

1. Enter WebXR and fetch capabilities from hardcoded service URLs.
2. Present reachable robot drivers as physical blocks.
3. The user taps one robot-driver block.
4. Filter processors against the selected driver's video profiles.
5. Present raw direct viewing and compatible processors as physical blocks.
6. The user taps one visual-mode block.
7. Create a driver session for the selected video profile and optional control.
8. Receive a destination-bound, read-only `VideoSource` descriptor from the
   driver.
9. For raw viewing, connect the client directly to that source.
10. Otherwise, create a processor session using the descriptor; the processor
   connects directly to the driver and the client connects to processor output.
11. Connect the client directly to driver telemetry and, when authorized,
   control.
12. Perform coordinate alignment, show health, then allow the user to enable
    motion.

The client tears down every session it created. Services also expire abandoned
sessions and release resources when their leases are not renewed.

## Authentication and Trust

The client is the orchestrator, but it is not automatically trusted.

- REST APIs authenticate users and authorize session creation.
- Driver video descriptors are short-lived, destination-bound capability tokens.
- A processor receives video-read permission only, never robot-control
  permission.
- Driver control sessions require a distinct permission and explicit ownership.
- Services validate the identity and destination bound into every descriptor.
- Hardcoded service URLs never contain session credentials.

## Failure Behavior

| Failure | Behavior |
|---|---|
| Driver video stalls | Processor reports degraded/lost input; client keeps the last renderable scene |
| Driver video stalls during raw viewing | Client marks the view stale and shows the last frame or a blank safe view |
| Processor loses tracking | Processor publishes lost state and freezes or resets its map |
| Processor crashes | Robot control remains direct and safe; client can select or restart a processor |
| Processor output is missed | Client requests a scene manifest and required chunks |
| Client is too slow | Processor drops tracking updates, then resynchronizes or disconnects |
| Client control stream stops | Driver watchdog performs the robot's safe stop |
| Client disconnects | Driver stops; processor and driver sessions expire |

The client must present these states clearly. It must never imply that a stale
scene is live or that a robot is stopped before the driver acknowledges the stop.

## Observability and Recording

Each service exposes session status and metrics through REST. Common metrics
include:

- source capture age, network delay, frame rate, and dropped frames;
- synchronization error and timestamp quality;
- encode, decode, copy, queue, and upload time;
- tracking state, map revision, scene size, and GPU memory;
- WebRTC round-trip time, loss, jitter, selected ICE path, and buffered bytes;
- command age, clamp events, watchdog stops, and driver errors.

Recording is a service feature, not a central-server feature. A driver can record
camera, calibration, telemetry, and commands. A processor can record its input
and scene output. Recordings use the same stream/profile schemas so they can be
replayed by test drivers and benchmarked by processors.

## Implementation Plan

### Milestone 1: Protocol and Client Orchestration

- Define service identity, capabilities, sessions, errors, and capability tokens.
- Configure a hardcoded initial service list.
- Implement the immersive block-based selection scene, compatibility filtering,
  session lifecycle, and health display.
- Implement a recorded robot driver and direct raw-video client renderer.
- Prove direct driver-to-processor, processor-to-client, and client-to-driver
  WebRTC connections.

### Milestone 2: Canonical ROS2 Driver and Safety

- Package the configurable ROS2 driver container.
- Support mono and stereo image topics, `CameraInfo`, TF, telemetry, and command
  topics.
- Preserve capture timestamps and validate synchronized stereo pairs.
- Implement alignment, command limits, ownership, enable state, and watchdog.
- Test DDS connectivity and commands without installing Ito software on the
  robot.

### Milestone 3: Gaussian Processing

- Implement one mono Gaussian processor behind the visual-processor API.
- Add chunked scene streaming, tracking metadata, acknowledgements, and resync.
- Measure end-to-end latency and recovery using recorded and live streams.
- Add metric-scale sources before enabling translation that depends on the map.

### Milestone 4: Performance and Additional Processors

- Implement stereo and RGB-D Gaussian processors.
- Benchmark ROS2 and move only measured hot paths to C++ when needed.
- Measure and optimize co-located WebRTC overhead.
- Add direct raw stereo client rendering.
- Test direct ICE, TURN fallback, overload, reconnect, and session expiry.

## Acceptance Criteria

- No live pose, video, splat, or telemetry data passes through an Ito
  application-level intermediary; TURN remains an explicit network fallback.
- The client can explain processor compatibility before starting a session.
- Processors and drivers can be changed independently through their common APIs.
- The canonical ROS2 driver works without installing Ito software on the robot.
- All streams preserve frame IDs, coordinate frames, and capture timestamps.
- Overload drops stale work instead of growing latency without bound.
- Reconnecting clients deterministically recover persistent scene state.
- Missing or stale client control always triggers a tested driver-side safe stop.
- Per-stage latency and the selected network path are visible to the user.
