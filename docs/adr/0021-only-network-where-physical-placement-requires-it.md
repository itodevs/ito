# ADR 0021: Use network transport only at physical boundaries

## Decision

The always-present boundary is Pilot client ↔ Ito application. Local robot input,
sensors, and reconstruction use calls and memory. External mode adds exactly one
driver boundary because robot and Ito are on different machines.

WebSocket carries MessagePack lifecycle and non-trickle signaling. WebRTC carries
replaceable pilot input, remote camera media when necessary, and binary Splat
Batches. Local camera frames never take a fake loopback transport path.
