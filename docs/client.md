# Ito Client

Browser-based WebXR client built with Three.js and A-Frame. Connects to the Ito server over WebRTC, receives 3D Gaussian splat data, and renders it in VR.

## Target platforms

- **PCVR** (desktop browser with a VD or SteamVR headset)
- **Quest** (standalone browser over WiFi)
- **Pico** (standalone browser over WiFi)

All targets run the same client. Quality settings for setting render resolution and splat count.

## Rendering

Splats are rendered using [Spark](https://github.com/sparkjsdev/spark), a Three.js Gaussian splatting library designed for dynamic scenes. It integrates directly into the Three.js rendering pipeline, so WebXR works natively. Sorting and LOD are handled by Spark.

Splats use RGB-only color. Set `maxSh = 0` on each `SplatMesh` to disable spherical harmonics entirely. View-dependent color is not needed because the operator's viewpoint is always close to the robot camera's pose.

The scene is split across multiple `SplatMesh` objects — one per SLAM keyframe or spatial region. Incoming delta messages are applied using `pushSplat()` for new splats and `packedSplats.setSplat(index, ...)` for modifications, followed by `packedSplats.needsUpdate = true` on only the affected mesh. This avoids re-uploading the full scene to the GPU every frame; static meshes from earlier keyframes remain untouched.

LOD can be enabled per mesh (`lod: true`) for Quest and Pico targets to reduce GPU load on weaker hardware.

## Transport

Connects to the Ito server over **WebRTC DataChannel**. Splat delta messages are binary. A small header per message includes frame ID, timestamp, and payload type. The server sends a full keyframe on first connect for initial sync.

## Architecture

Three independent loops run at different rates:

1. **Network receive loop**: receives splat delta messages from the server, updates the local splat store
2. **Render loop**: runs at 90Hz, reads the current splat store and renders from the operator's current head pose via WebXR
3. **Pose send loop**: sends the operator's current head pose to the server so the robot can match it

The render loop never waits for the network. It always renders from whatever scene data it currently has. The 3D scene provides visual stability between frame arrivals.

## No Local SLAM

All reconstruction happens on the server. The client is a pure renderer. The only data it sends is the operator's body pose (based on headset, controllers and optionally other trackers); the only data it receives is splat deltas.
