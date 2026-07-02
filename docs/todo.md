# Ito v1 TODO

Reference docs are canonical: `README.md`, `docs/v1.md`, `docs/protocol.md`, and `docs/adr/`.
Keep task details in those docs rather than duplicating them here.

1. [ ] Define the v1 protocol payload tables missing from `docs/protocol.md`.
2. [ ] Create the shared protocol constants and MessagePack envelope helpers.
3. [ ] Add protocol-version validation and Display Reason helpers.
4. [ ] Scaffold the Python Ito Server application and container.
5. [ ] Implement server configuration from environment variables.
6. [ ] Implement server WebSocket accept, hello, routing, and request timeouts.
7. [ ] Implement robot-driver connection tracking and status watchdogs.
8. [ ] Implement the in-memory Robot Catalog.
9. [ ] Implement duplicate `robotId` detection.
10. [ ] Implement pilot-client catalog requests.
11. [ ] Implement server-side acquisition reservation.
12. [ ] Implement driver session-start request/result handling.
13. [ ] Implement server-owned session allocation.
14. [ ] Implement session end and `session.ended` fan-out.
15. [ ] Implement session cleanup for disappeared endpoints.
16. [ ] Implement reconnect hello handling for resumable sessions.
17. [ ] Add server tests for catalog, acquisition, lifecycle, and reconnect behavior.
18. [ ] Scaffold the Mock Robot driver and container.
19. [ ] Implement Mock Robot status reporting.
20. [ ] Implement Mock Robot acquisition and session lifecycle handling.
21. [ ] Implement Mock Robot pilot-input reception and logging.
22. [ ] Add video-file-backed Mock Robot camera input.
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
38. [ ] Scaffold the plain-JavaScript Pilot Client.
39. [ ] Implement the browser Enter VR launch surface.
40. [ ] Implement client configuration defaults and Local Storage settings.
41. [ ] Add pilot-facing text resource loading.
42. [ ] Implement in-VR controller-ray UI foundations.
43. [ ] Implement the in-VR Robot Catalog.
44. [ ] Implement acquisition and connecting states in VR.
45. [ ] Implement session view with Spark.JS Splat Scene ownership.
46. [ ] Implement Splat Lifetime and Splat Budget eviction.
47. [ ] Implement headset-yaw Pilot Input Snapshots.
48. [ ] Implement client visual-freshness timeout behavior.
49. [ ] Implement in-VR menu pause and session end action.
50. [ ] Implement session-ended popup and return-to-catalog flow.
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
