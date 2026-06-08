# Ito Client

The Ito client is the leading application in the Ito architecture. It is a
browser-based WebXR application built with Three.js. It enters WebXR as soon as
possible, lets the user physically select robot-driver and visual-processor
blocks, connects the selected sessions, renders their output, and sends operator
input directly to the robot driver.

The client does not reconstruct scenes and does not forward video, splats,
telemetry, or control data between services.

## Target Platforms

The first supported deployment is:

- **PCVR**: a Windows browser with a standalone headset connected through
  Virtual Desktop and a Windows OpenXR runtime. Services run as Docker containers
  using Docker Engine inside WSL2.

Possible later targets are standalone Quest and Pico browsers over WiFi, plus a
desktop diagnostics mode. They should use the same client application, but will
require separate work for secure hosting, network reachability, rendering
limits, and codec support.

## Responsibilities

The client owns:

- loading hardcoded service URLs and inspecting their capabilities;
- robot-driver and visual-processor compatibility filtering;
- session creation, renewal, and teardown;
- direct WebRTC connections to selected services;
- coordinate-frame composition and client/robot alignment;
- raw-video and Gaussian-splat rendering;
- headset and controller pose sampling;
- control ownership, enable state, and operator-facing stop controls;
- health, latency, stale-data, and partial-failure presentation.

Robot drivers remain responsible for enforcing command limits and the final
safety watchdog. Visual processors remain responsible for reconstruction state,
tracking health, and scene synchronization.

## Immersive Setup

The client enters WebXR immediately and shows a simple setup space.

Robot drivers from a hardcoded service list appear as physical blocks. Each block
shows the driver's name, connection health, and a small amount of useful status.
The user selects a robot by reaching out and tapping its block.

After robot selection, the client filters visual processors against the selected
video profile. Compatible processors and raw direct viewing appear as a second
set of physical blocks. Incompatible processors are hidden or visibly disabled
with a concise reason. The user taps one block to start that visual mode.

The first version does not support discovery or editing service URLs. Dynamic
service configuration can be designed later. Hardcoded URLs must never contain
session credentials.

## Session Orchestration

The client creates a session graph rather than connecting to one Ito server:

```text
client -- control -----------> robot driver
client <-- telemetry --------- robot driver
client <-- raw video --------- robot driver       # raw-view mode only
robot driver -- video -------> visual processor   # processed mode only
client <-- scene/tracking ---- visual processor   # processed mode only
```

The setup sequence is:

1. Enter WebXR and fetch capabilities from hardcoded service URLs.
2. Show robot-driver blocks and let the user tap one.
3. Show compatible visual-mode blocks and let the user tap one.
4. Create a driver session and receive a destination-bound `VideoSource`.
5. For raw viewing, connect directly to the driver's video source.
6. For processed viewing, create a processor session using the `VideoSource`,
   then connect directly to the processor output.
7. Connect directly to driver telemetry and, when authorized, control.
8. Perform coordinate alignment.
9. Allow the user to enable motion.

The client renews active session leases and tears down every session it creates.
It must handle a driver or processor becoming unavailable without leaving the
other sessions or the robot in an unsafe state.

## WebRTC Connections

REST is used only for service identity, capabilities, session setup, status, and
teardown. All live data uses direct WebRTC connections.

### Robot Driver Connection

| Stream/channel | Delivery | Direction | Contents |
|---|---|---|---|
| `control` | unordered, no retransmission | client to driver | newest operator pose and enable state |
| `telemetry` | unordered, limited retransmission | driver to client | robot transforms and state |
| `events` | reliable, ordered | both | ownership, calibration, errors, stop acknowledgements |
| video tracks | RTP | driver to client | raw-view mode only |

### Visual Processor Connection

| Channel | Delivery | Direction | Contents |
|---|---|---|---|
| `scene` | reliable, unordered | processor to client | versioned chunk snapshots, replacements, removals, and map resets |
| `tracking` | unordered, limited retransmission | processor to client | camera pose, tracking health, scale status |
| `events` | reliable, ordered | both | session state, errors, resync requests and acknowledgements |

The client prefers direct ICE paths. It reports when TURN is selected because
the relay adds latency.

## Render Modes

### Gaussian Scene

Gaussian scenes are rendered using
[Spark](https://github.com/sparkjsdev/spark), a Three.js Gaussian-splatting
library with WebXR support.

The scene is split into independently replaceable chunks, normally by keyframe
or spatial region. Each chunk maps to one renderable splat object and has a
stable ID, version, transform into `map`, and optional LOD variants.

When a chunk arrives, the client:

1. reassembles any fragments;
2. rejects stale or superseded versions;
3. creates or replaces only the affected renderable object;
4. records the applied scene revision;
5. acknowledges the revision to the processor.

On connect, reconnect, revision gap, or map reset, the client requests a manifest
and the required chunk snapshots. It never depends on mutable global splat
indices.

Compact RGB splats are the initial representation. Spherical harmonics and other
representations are enabled only when both the client and processor advertise
support. Device-specific scene limits and LOD keep standalone headsets usable.

### Raw Video

Raw-view mode connects directly to browser-compatible RTP tracks from the robot
driver. Mono video is rendered as a head-locked or world-aligned view according
to the selected mode. Stereo video is rendered to the corresponding eyes only
when its calibration, synchronization, and layout are valid.

Raw viewing does not start a visual processor. The client displays calibration,
latency, and stale-frame warnings because raw video provides no reconstructed
view for latency compensation.

## Coordinate Frames

The client composes transforms from three owners:

| Owner | Frames |
|---|---|
| Robot driver | `robot_base`, `robot_head`, robot eyes, and cameras |
| Visual processor | `map -> camera_left` |
| Client | `client_origin`, headset, and controllers |

Every received transform includes parent and child frame IDs, timestamp, and
clock domain. The client uses these to place robot metadata, including current
head and eye positions, in the reconstructed scene.

Before control is enabled, the client and driver establish an explicit alignment
between the operator and robot. Commands are relative to this alignment, never
raw WebXR coordinates. Recenter events pause control until the alignment is
validated again.

## Independent Loops

The client runs independent loops at different rates:

1. **Render loop**: runs at the headset refresh rate and never waits for network
   data.
2. **Scene/video receive loop**: applies the newest complete visual updates.
3. **Tracking receive loop**: updates camera pose and reconstruction health.
4. **Telemetry receive loop**: updates robot transforms and state.
5. **Control send loop**: samples operator pose and sends the newest command.
6. **Session loop**: renews leases, polls status, and handles reconnects.

The render loop always uses the most recent valid state. When data becomes stale,
the client clearly marks it as stale rather than presenting it as live.

## Control and Safety UX

The client requests control ownership from the robot driver. Motion remains
disabled until:

- the driver grants ownership;
- alignment is valid;
- required tracking is healthy;
- the user explicitly enables motion.

Control messages include sequence numbers and client monotonic timestamps. The
client sends only the newest pose and does not retransmit stale control samples.

The client exposes a prominent stop action and waits for the driver's stop
acknowledgement. On lost focus, WebXR session end, recentering, stale tracking,
driver disconnect, or client error, it stops sending enabled commands. The
driver's watchdog remains the authority that safely stops the robot.

## Health and Failure Presentation

The client separately displays:

- robot-driver connectivity and control ownership;
- visual-processor connectivity and tracking state;
- video capture age and synchronization quality;
- scene revision and stale-data age;
- WebRTC path, round-trip time, jitter, and packet loss;
- scale status and whether translation is safe;
- current command age and latest stop acknowledgement.

A failed visual processor must not interrupt direct robot control, but the client
may disable motion when visual feedback is no longer safe. A disconnected driver
ends control immediately. A stale scene remains renderable only with an obvious
warning.

## No Local Reconstruction

Reconstruction remains outside the client. The client receives raw video or a
renderable scene from a selected service and concentrates on orchestration,
rendering, interaction, and clear safety state.

## First Implementation

1. Load a hardcoded service list and enter WebXR immediately.
2. Implement immersive robot-driver and visual-processor blocks, compatibility
   filtering, and session lifecycle.
3. Connect the mock driver to the mock mono processor through direct WebRTC
   video.
4. Implement direct pose/control and telemetry WebRTC channels.
5. Implement chunked Gaussian-scene rendering, acknowledgements, and resync.
6. Add coordinate alignment, health presentation, and safe control UX.

Raw-video rendering, stereo processing, discovery, LAN access, and standalone
headset browsers follow after this first vertical slice.
