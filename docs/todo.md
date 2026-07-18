# Ito work

## Implemented foundation

- [x] One Ito application hosts the WebXR client and `/ws` endpoint.
- [x] One pilot connects directly and explicitly starts/stops control.
- [x] Catalog, browsing, allocation, reservation, stable robot IDs, fleet
  heartbeats, and competing-pilot locking are removed.
- [x] Local robot adapter moves sensor frames and pilot input in-process.
- [x] Remote robot adapter and lightweight mock driver preserve the low-spec
  external deployment option without changing the pilot protocol.
- [x] Pilot input and Splat Batch WebRTC paths terminate at the Ito endpoint in
  onboard mode.
- [x] Robot-local timeout and neutralization behavior remains in Ito Droid.
- [x] One-container Compose deployment serves the client.

## Next concrete work

- [ ] Select and integrate the first onboard reconstruction algorithm against
  the existing `ReconstructionProcessor` seam.
- [ ] Connect a production local adapter to Ito Droid ROS sensor and actuator
  APIs so the physical reference robot uses onboard mode.
- [ ] Complete Ito Droid camera WebRTC publishing for the external fallback;
  the mock remote driver currently exercises the complete fallback transport.
- [ ] Run Pico 4 hardware acceptance for control, visual freshness, disconnect,
  and safe resumption.
- [ ] Measure end-to-end latency and avoidable copies in both placement modes.
