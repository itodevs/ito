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
24. [ ] Implement client-to-driver WebRTC pilot-input data channel.
25. [ ] Implement server-to-client WebRTC Splat Batch data channel.
26. [ ] Add non-trickle WebRTC signaling over the WebSocket control plane.
27. [ ] Record representative USB-webcam reconstruction test sequences.
28. [ ] Spike MASt3R-SLAM on the recorded sequences.
29. [ ] Spike MonoGS on the recorded sequences.
30. [ ] Select the v1 monocular reconstruction path.
31. [ ] Define the server-internal reconstruction processor interface.
32. [ ] Integrate the selected processor under `server/processors/`.
33. [ ] Implement camera media decoding into reconstruction frames.
34. [ ] Implement reconstruction failure isolation per session.
35. [ ] Spike Spark.JS Splat Batch insertion on Pico 4.
36. [ ] Freeze the v1 Splat Batch binary layout.
37. [ ] Implement server Splat Batch encoding.
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
52. [ ] Scaffold the Ito Droid ROS driver and container.
53. [ ] Implement Ito Droid environment-based configuration.
54. [ ] Implement Ito Droid status reporting.
55. [ ] Consume the configured ROS camera feed.
56. [ ] Publish camera media to the server over WebRTC.
57. [ ] Receive Pilot Input Snapshots from the client.
58. [ ] Implement yaw-to-camera-pan servo mapping.
59. [ ] Implement driver control tick processing.
60. [ ] Implement pilot-input timeout behavior.
61. [ ] Implement safe control resumption ramping.
62. [ ] Implement session-start servo neutralization.
63. [ ] Implement clean session-end servo neutralization.
64. [ ] Add driver tests around mapping, timeout, and lifecycle behavior.
65. [ ] Add end-to-end Mock Robot tests over WebSocket and WebRTC.
66. [ ] Add end-to-end Ito Droid smoke testing on physical hardware.
67. [ ] Document Docker Compose commands for local v1 operation.
68. [ ] Run a full v1 acceptance pass against the core outcome.
