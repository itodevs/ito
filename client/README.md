# Pilot Client

The Pilot Client is the WebXR application used by the pilot to perceive through
and control a robot.

The v1 client is a static, plain-JavaScript A-Frame/WebXR application. The
non-VR page only exposes the browser-required Enter VR launch action; catalog,
acquisition, settings, session state, and session end controls are rendered in
VR.

## Run locally

From this directory:

```sh
python -m http.server 8080
```

Then open `http://localhost:8080/`. The client defaults to the Ito Server
control WebSocket at `ws://<page-host>:8765` and stores runtime settings in
browser Local Storage under `ito.pilotClient.settings.v1`.

## Tests

The client uses Node's built-in test runner and has no npm dependencies.

```sh
npm test
```

## Implementation notes

- WebSocket control-plane messages are MessagePack-encoded Ito envelopes.
- Pilot-facing text is loaded from `resources/en/default.json` and resolved by
  resource key before falling back to driver/server free text.
- The Splat Scene is client-owned. `src/splat-scene.js` includes the Spark.JS
  adapter seam and v1 Splat Batch binary header parser. Exact Spark insertion
  performance still needs Pico 4 validation.
- Pilot Input Snapshots are generated at the configured rate with headset yaw
  relative to session start plus current controller state. `src/webrtc.js`
  creates non-trickle WebRTC offers for pilot-input and Splat Batch data
  channels over the WebSocket control plane.
