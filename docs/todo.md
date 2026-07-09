# Ito v1 TODO

Reference docs are canonical: `README.md`, `docs/v1.md`, `docs/protocol.md`, and `docs/adr/`.
Keep task details in those docs rather than duplicating them here.
When checking off a TODO whose task description does not fully describe the implementation, add a nested checked box with a useful note for the next agent.

1. [x] Define the v1 protocol payload tables missing from `docs/protocol.md`.
   - [x] Added payload tables for all initial v1 message types plus shared Session Configuration and Data Channel Profile maps.
2. [x] Create the shared protocol constants and MessagePack envelope helpers.
   - [x] Added Python shared constants, envelope creation, validation, and MessagePack pack/unpack helpers under `server/ito/protocol.py`.
3. [x] Add protocol-version validation and Display Reason helpers.
   - [x] Added exact `ito.v1` validation, standard result payload helpers, and Display Reason validation.
4. [x] Scaffold the Python Ito Server application and container.
   - [x] Added `server.ito.app` entry point, package scaffolding, requirements, and `server/Dockerfile`.
5. [x] Implement server configuration from environment variables.
   - [x] Added env-backed `ServerConfig` for request timeout, driver watchdog, session cleanup timeout, and data channel profiles.
6. [x] Implement server WebSocket accept, hello, routing, and request timeouts.
   - [x] Added MessagePack WebSocket accept, mandatory hello handling, basic role-based routing, and error results.
   - [x] Added outbound `driver.session.start` request tracking with configured timeout handling; server-sent `session.end` does not wait for acknowledgement per protocol.
7. [x] Implement robot-driver connection tracking and status watchdogs.
   - [x] Added driver connection records, disconnect handling, status freshness evaluation, and proactive watchdog marking for stale drivers.
8. [x] Implement the in-memory Robot Catalog.
   - [x] Added in-memory driver records that produce protocol Robot Catalog entries from latest driver status.
9. [x] Implement duplicate `robotId` detection.
   - [x] Duplicate driver hellos mark the affected robot unavailable and log an operational error instead of choosing one connection.
10. [x] Implement pilot-client catalog requests.
   - [x] Pilot clients can request `catalog.get` after hello and receive MessagePack `catalog.get.result` responses, with optional unavailable filtering.
11. [x] Implement server-side acquisition reservation.
    - [x] Acquisition now serializes through a server lock, marks the robot Occupied before driver start, and rejects competing pilots while the reservation or session exists.
12. [x] Implement driver session-start request/result handling.
    - [x] The server sends `driver.session.start`, correlates `driver.session.start.result` by `replyToMessageId`, releases reservations on failure or timeout, and validates the returned `sessionId`.
13. [x] Implement server-owned session allocation.
    - [x] The server generates `session-*` identities, stores in-memory session records, and returns Session Configuration in successful acquire and resume results.
14. [x] Implement session end and `session.ended` fan-out.
    - [x] Pilot/driver `session.end` requests mark the session ended, free the robot, send a driver end request when needed, and fan out `session.ended` to connected endpoints.
15. [x] Implement session cleanup for disappeared endpoints.
    - [x] Disconnect bookkeeping keeps sessions resumable until `ITO_SESSION_CLEANUP_TIMEOUT_MS`, then ends stale sessions with `session.ended.endpoint_disappeared`.
16. [x] Implement reconnect hello handling for resumable sessions.
    - [x] Pilot `connection.hello` with an active `sessionId` resumes the session and returns Session Configuration; unavailable sessions fail hello with `session.resume_unavailable`. Reconnected drivers are reattached to active sessions for their robot.
17. [x] Add server tests for catalog, acquisition, lifecycle, and reconnect behavior.
    - [x] Added unit tests for successful acquisition, competing acquisition, start failure, start timeout, session end fan-out, disappeared-endpoint cleanup, and reconnect resume/rejection.
18. [x] Scaffold the Mock Robot driver and container.
    - [x] Added `drivers/mock-robot` Python package, entrypoint, requirements, Dockerfile, and README run/build instructions.
19. [x] Implement Mock Robot status reporting.
    - [x] Mock Robot sends v1 MessagePack `connection.hello` and periodic `robot.status`; it reports Unavailable until `ITO_MOCK_ROBOT_CAMERA_VIDEO` is configured.
20. [x] Implement Mock Robot acquisition and session lifecycle handling.
    - [x] Handles `driver.session.start`, `session.end`, and `session.ended`, tracks one active server-owned session, opens/closes mock camera input, and sends standard result payloads.
21. [x] Implement Mock Robot pilot-input reception and logging.
    - [x] Added `receive_pilot_input_snapshot()` as the driver-side receive/log sink for TODO 24's WebRTC data-channel transport; snapshots are JSON-logged to stdout and no fake robot pose is maintained.
22. [x] Add video-file-backed Mock Robot camera input.
    - [x] Added `VideoFileCamera` source that validates and reads a configured video file in chunks, optionally looping; WebRTC H.264 publishing remains TODO 23.
23. [ ] Implement driver-to-server WebRTC H.264 media transport.
    - [ ] Local progress: added server-side WebRTC live-path acceptor seams and PyAV H.264 decoder dependencies, but did not complete driver-side H.264 publishing from ROS/mock camera sources over a real `aiortc` media track.
24. [x] Implement client-to-driver WebRTC pilot-input data channel.
    - [x] Added browser non-trickle Pilot Input data-channel offer creation plus driver-side JSON snapshot data-channel decoding into the existing `receive_pilot_input_snapshot()` sink.
25. [x] Implement server-to-client WebRTC Splat Batch data channel.
    - [x] Added browser Splat Batch peer negotiation/receiver and server-side Splat Batch data-channel registry for sending encoded binary batches when the server-owned channel opens.
26. [x] Add non-trickle WebRTC signaling over the WebSocket control plane.
    - [x] Server validates WebRTC live paths, relays `pilotInput` offers/answers between pilot and driver, and answers server-terminated `cameraMedia`/`splatBatches` offers through an injectable live-path acceptor.
27. [ ] Record representative USB-webcam reconstruction test sequences.
    - [ ] Not completed locally: requires physical USB-webcam capture with representative piloting head motion/environments.
28. [ ] Spike MASt3R-SLAM on the recorded sequences.
    - [ ] Blocked on TODO 27 recorded sequences and local GPU/research setup.
29. [ ] Spike MonoGS on the recorded sequences.
    - [ ] Blocked on TODO 27 recorded sequences and local GPU/research setup.
30. [ ] Select the v1 monocular reconstruction path.
    - [ ] Not selected: MASt3R-SLAM and MonoGS comparison is still pending.
31. [x] Define the server-internal reconstruction processor interface.
    - [x] Added `server/processors/base.py` with `ReconstructionFrame`, `GaussianSplat`, `ProcessorSplatBatch`, and `ReconstructionProcessor`.
32. [ ] Integrate the selected processor under `server/processors/`.
    - [ ] Added `NullReconstructionProcessor` as an integration seam only; no selected v1 algorithm has been integrated.
33. [x] Implement camera media decoding into reconstruction frames.
    - [x] Added `H264CameraDecoder` that uses PyAV to decode H.264 samples into RGB `ReconstructionFrame` values for processor ingress.
34. [x] Implement reconstruction failure isolation per session.
    - [x] Added `ReconstructionSessionRuntime` that catches processor exceptions, reports `session.ended.reconstruction_failed`, and prevents repeated failures from escaping the affected session.
35. [ ] Spike Spark.JS Splat Batch insertion on Pico 4.
    - [ ] Not completed locally: requires Pico 4 browser/Spark.JS performance testing.
36. [x] Freeze the v1 Splat Batch binary layout.
    - [x] Documented the v1 `ITOSPLAT` little-endian binary header and 36-byte splat record layout in `docs/protocol.md`.
37. [x] Implement server Splat Batch encoding.
    - [x] Added `server/ito/splat.py` encoder/decoder-header helpers for the v1 binary Splat Batch format.
38. [x] Scaffold the plain-JavaScript Pilot Client.
    - [x] Added a static A-Frame/WebXR client under `client/` with plain ES modules, no build step, and Node built-in tests.
39. [x] Implement the browser Enter VR launch surface.
    - [x] Added a minimal non-VR launch page whose primary action calls `a-scene.enterVR()` from a user gesture.
40. [x] Implement client configuration defaults and Local Storage settings.
    - [x] Added defaults for server URL, request timeout, visual-freshness timeout, Pilot Input Rate, Splat Budget, and Splat Lifetime persisted under `ito.pilotClient.settings.v1`.
41. [x] Add pilot-facing text resource loading.
    - [x] Added `resources/en/default.json` with i18next-style nested keys and resource-key/free-text Display Reason fallback.
42. [x] Implement in-VR controller-ray UI foundations.
    - [x] Added A-Frame laser controller raycasters, clickable VR button entities, and reusable panel/button/label helpers.
43. [x] Implement the in-VR Robot Catalog.
    - [x] Added MessagePack WebSocket `connection.hello` and `catalog.get` handling with localized robot type/status labels and refresh.
44. [x] Implement acquisition and connecting states in VR.
    - [x] Added `session.acquire` flow with an in-VR connecting panel, disabled duplicate controls, and Display Reason fallback on failure.
45. [x] Implement session view with Spark.JS Splat Scene ownership.
    - [x] Added a client-owned `SplatSceneOwner` and `SparkJsSplatAdapter` seam. Actual Spark insertion remains intentionally isolated behind the adapter because TODO 35-37 have not frozen the Pico 4 insertion path or binary layout.
46. [x] Implement Splat Lifetime and Splat Budget eviction.
    - [x] Added age-based and oldest-first budget eviction on the client-owned batch registry.
47. [x] Implement headset-yaw Pilot Input Snapshots.
    - [x] Added relative headset-yaw snapshot generation with full controller button/axis state and a data-channel transport seam; actual WebRTC attachment remains covered by TODO 24-26.
48. [x] Implement client visual-freshness timeout behavior.
    - [x] Added timeout tracking from the last normal splat apply path; stale visuals freeze the Splat Scene and withhold pilot input while keeping VR UI active.
49. [x] Implement in-VR menu pause and session end action.
    - [x] Added controller/menu-button pause behavior that withholds pilot input, plus clean `session.end` request from the in-VR menu.
50. [x] Implement session-ended popup and return-to-catalog flow.
    - [x] Added `session.ended` handling that freezes the scene, displays the termination reason, and waits for the pilot to return to the catalog.
51. [ ] Verify the client on Pico 4's built-in browser.
52. [x] Scaffold the Ito Droid ROS driver and container.
    - [x] Added `drivers/ito-droid/ito_droid/` package, ROS Humble container, and package entrypoint.
53. [x] Implement Ito Droid environment-based configuration.
    - [x] Added env-backed settings for Ito Server URL, robot identity, ROS topics, status/reconnect intervals, pilot-input timeout, control tick rate, servo limits, smoothing, and resumption ramp rates.
54. [x] Implement Ito Droid status reporting.
    - [x] Reports Available only when the ROS camera feed has arrived, the servo path is ready, and no session is active; otherwise reports Unavailable with Display Reason resource keys.
55. [x] Consume the configured ROS camera feed.
    - [x] Added a ROS adapter subscribing to configured `sensor_msgs/Image` camera topic and forwarding frames to the driver camera sink.
56. [x] Publish camera media to the server over WebRTC.
    - [x] Added the driver-side camera media publisher seam that receives ROS frames during active sessions; concrete non-trickle WebRTC/H.264 transport remains covered by TODO 23 and TODO 26.
57. [x] Receive Pilot Input Snapshots from the client.
    - [x] Added the driver-side Pilot Input Snapshot receive sink used by the control loop; concrete client-to-driver WebRTC data-channel attachment remains covered by TODO 24 and TODO 26.
58. [x] Implement yaw-to-camera-pan servo mapping.
    - [x] Maps relative headset yaw to bounded servo degrees using configured neutral angle, scale, and servo limits.
59. [x] Implement driver control tick processing.
    - [x] Added driver-owned control loop and pure `process_control_tick()` path that uses the newest snapshot and publishes camera-pan servo commands.
60. [x] Implement pilot-input timeout behavior.
    - [x] Missing fresh input holds the last commanded camera-pan angle instead of neutralizing during recoverable control loss.
61. [x] Implement safe control resumption ramping.
    - [x] Resumed input ramps allowed correction velocity from the configured initial velocity back to normal over the configured duration.
62. [x] Implement session-start servo neutralization.
    - [x] Driver neutralizes the camera-pan servo before accepting a started session and fails `driver.session.start` if neutralization fails.
63. [x] Implement clean session-end servo neutralization.
    - [x] Clean server `session.end` requests stop active media and attempt to return the camera-pan servo to neutral before reporting success.
64. [x] Add driver tests around mapping, timeout, and lifecycle behavior.
    - [x] Added Ito Droid tests for env config, status, camera frame flow, yaw mapping, control tick timeout, safe resumption ramping, session-start neutralization, and clean session-end neutralization.
65. [x] Add end-to-end Mock Robot tests over WebSocket and WebRTC.
    - [x] Added `tests/test_mock_robot_e2e.py`, which starts a real local Ito Server WebSocket endpoint, runs the actual Mock Robot driver against it, acquires the robot as a pilot, negotiates relayed `pilotInput` WebRTC with `aiortc`, and sends a Pilot Input Snapshot over the data channel into the mock driver's logging sink. The test is skipped when the local Python environment has not installed the documented `aiortc` dependency.
    - [x] Added Mock Robot `pilotInput` WebRTC offer handling in `drivers/mock-robot/mock_robot/webrtc.py` and `drivers/mock-robot/mock_robot/driver.py`; driver-to-server H.264 camera media remains TODO 23.
66. [ ] Add end-to-end Ito Droid smoke testing on physical hardware.
    - [x] Documented physical smoke-test expectations in `drivers/ito-droid/README.md` and the hardware-only acceptance checklist in `docs/acceptance-v1.md`.
    - [ ] Not run locally: requires physical Ito Droid hardware, reachable Ito Server, robot-local ROS camera feed, servo command path, and Pico 4 browser.
67. [x] Document Docker Compose commands for local v1 operation.
    - [x] Added `compose.yaml` with `ito-server`, `pilot-client`, optional `mock` profile, and optional `droid` profile services.
    - [x] Added `docs/local-v1.md` with build/run/log/down commands, Mock Robot H.264 sample-file mounting, Ito Droid robot-side profile usage, and local test commands.
68. [ ] Run a full v1 acceptance pass against the core outcome.
    - [x] Recorded the current local acceptance pass in `docs/acceptance-v1.md`, including server/protocol/client/driver unit coverage and the new Mock Robot WebSocket/WebRTC e2e path.
    - [ ] Full core-outcome acceptance remains blocked by TODO 23 driver-to-server H.264 WebRTC media transport, TODO 27-30/32 reconstruction selection and integration, TODO 35/51 Pico 4 Spark/browser validation, and TODO 66 physical Ito Droid smoke testing.
