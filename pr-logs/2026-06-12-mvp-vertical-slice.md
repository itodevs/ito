# MVP vertical slice decisions

## 2026-06-12: Merge the now in-tree components

The updated `main` branch removes the remaining submodules and provides the
previously unavailable client and robot reference documentation. This branch
merged that work, retained the detailed `client/README.md`, and treats all
components as ordinary in-tree code.

## 2026-06-12: Stream the Gaussian-splat PLY directly into SparkJS

The mounted `.ply` is a Gaussian-splat scene, not an ordinary polygon or point
cloud. The processor validates representative Gaussian attributes, then sends a
small stream header followed by bounded ordered binary chunks. The A-Frame client receives those chunks incrementally and renders the
Gaussian-splat PLY with SparkJS instead of the previous PLYLoader point cloud.
The later compatibility decision below documents why the client must retain one
completed input buffer.

## 2026-06-12: Use A-Frame entities for immersive interaction

The setup choices, controller touch spheres, raw-video surface, and Enable/Stop
blocks are declared in `client/index.html`. Small JavaScript handlers coordinate
networking and touch contact while A-Frame owns WebXR lifecycle and tracking.
This keeps the scene convenient to edit without introducing a frontend build.

## 2026-06-12: Keep localhost hosting plain and containerized

The client image is based directly on `nginx:latest`; there is no Node build,
certificate generation, CORS middleware, or HTTPS configuration. Host networking
remains because direct local ICE candidates and the processor-to-driver loopback
URL must be reachable without a TURN service or dynamic WebRTC port mappings.

## 2026-06-12: Remove generated tests from this implementation PR

Per review feedback, this PR removes the tests written alongside the original
implementation. Validation is limited to syntax, dependency installation,
container configuration/build, and manual runtime checks rather than treating
self-authored tests as evidence of correctness.

## 2026-06-12: Share A-Frame's Three.js runtime with Spark

The first Fedora/Podman browser run failed before entering VR with a duplicate
Three.js warning and `Can not resolve #include <splatDefines>`. A-Frame was
running its bundled Three.js while Spark registered its shader chunk on a
separate Three.js 0.180 module. The client now follows Spark's official A-Frame
integration pattern: module A-Frame, Spark, and `super-three` all resolve through
the same import map. Spark 0.1.8 is used because it is the release demonstrated
with A-Frame 1.7.1's `super-three` 0.177 runtime; Spark 2.x requires newer Three.js
renderer behavior.

That compatible Spark release accepts completed `fileBytes`, not a
`ReadableStream`. The scene still travels incrementally as bounded DataChannel
messages, but the client writes them into one preallocated PLY buffer before
handing it to Spark. The current 3.46 GB demo scene is likely to exceed practical
browser memory, so the client logs an explicit warning for scenes over 1 GB.
