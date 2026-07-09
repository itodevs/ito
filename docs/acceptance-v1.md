# v1 Acceptance Pass

This file records the current v1 acceptance pass against the core outcome in
`docs/v1.md`. Hardware-only acceptance remains unchecked until it is performed
with a physical Ito Droid and Pico 4 browser.

## Latest Local Run

Run on July 9, 2026:

- [x] `pytest -q`: 40 passed, 1 skipped. The skipped test is the Mock Robot
  `aiortc` WebRTC e2e test because this local Python environment does not have
  `aiortc` installed.
- [x] `npm test` from `client/`: 15 passed.
- [ ] `docker compose config`: not run because Docker is not installed in this
  environment.
- [ ] `python -m pip install -r server/requirements.txt -r drivers/mock-robot/requirements.txt`:
  attempted, but PyAV built from source and failed because FFmpeg development
  libraries were unavailable through `pkg-config`.

## Local Acceptance

- [x] Ito Protocol control-plane envelope tests pass for MessagePack binary
  WebSocket messages, exact `ito.v1` protocol-version validation, Display
  Reason helpers, and standard result payloads.
- [x] Ito Server unit tests cover pilot hello, catalog responses, driver status,
  duplicate `robotId` handling, serialized acquisition, session allocation,
  session end fan-out, disappeared-endpoint cleanup, and pilot reconnect resume
  or rejection.
- [x] Mock Robot unit tests cover status reporting, video-file-backed camera
  opening/closing, session start/end handling, session-start failure without a
  configured camera file, and Pilot Input Snapshot logging.
- [x] Mock Robot end-to-end test covers real MessagePack WebSocket control
  connections through the Ito Server, catalog acquisition, relayed
  `pilotInput` WebRTC offer/answer signaling, and delivery of a Pilot Input
  Snapshot over a real `aiortc` data channel when `aiortc` is installed.
- [x] Ito Droid unit tests cover environment configuration, status reporting,
  ROS camera frame ingress seams, yaw-to-servo mapping, control tick behavior,
  pilot-input timeout, safe resumption ramping, session-start neutralization,
  and clean session-end neutralization.
- [x] Pilot Client Node tests cover config persistence, i18n fallback,
  protocol helpers, Pilot Input Snapshot generation, Splat Batch parsing,
  Splat Scene ownership/eviction, visual-freshness timeout, and WebRTC
  non-trickle offer handling seams.

## Hardware-Only Acceptance Still Required

- [ ] Verify the Pilot Client on Pico 4's built-in browser, including Enter VR,
  controller-ray catalog interaction, acquisition, in-VR settings/menu pause,
  session end, and session-ended popup behavior.
- [ ] Run the Ito Droid driver on physical robot hardware with the configured
  ROS camera topic available and the camera-pan servo command topic connected.
- [ ] Confirm the physical session-start procedure moves the camera-pan servo to
  neutral before accepting pilot input.
- [ ] Confirm pilot headset yaw controls the physical camera-pan servo within
  configured limits and smoothing/rate limits.
- [ ] Confirm recoverable control loss by withholding pilot input for at least
  the configured timeout; the servo should hold the last commanded position.
- [ ] Confirm safe control resumption ramps correction velocity rather than
  snapping the servo after control loss.
- [ ] Confirm clean session end attempts to return the physical camera-pan servo
  to neutral.
- [ ] Confirm end-to-end robot camera media over WebRTC H.264 once TODO 23 is
  complete, then confirm reconstruction frames and Splat Batches reach the Pico
  4 client with the visual-freshness behavior described in `docs/v1.md`.

## Current Gaps

- TODO 23 is still open: driver-to-server WebRTC H.264 media transport is not
  complete, so the full live reconstruction loop cannot be accepted locally or
  on hardware yet.
- TODO 27-30 and TODO 32 are still open: the representative reconstruction
  sequences, algorithm spike/selection, and selected processor integration are
  not complete.
- TODO 35 and TODO 51 are still open: Spark.JS insertion performance and Pico 4
  browser acceptance require the headset.
