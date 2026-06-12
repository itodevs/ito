# MVP vertical slice decisions

## 2026-06-12: Merge the now in-tree components

The updated `main` branch removes the remaining submodules and provides the
previously unavailable client and robot reference documentation. This branch
merged that work, retained the detailed `client/README.md`, and treats all
components as ordinary in-tree code.

## 2026-06-12: Stream the Gaussian-splat PLY directly into SparkJS

The mounted `.ply` is a Gaussian-splat scene, not an ordinary polygon or point
cloud. The processor validates representative Gaussian attributes, then sends a
small stream header followed by bounded ordered binary chunks. The A-Frame
client passes those chunks into SparkJS through a `ReadableStream`, avoiding the
previous PLYLoader point-cloud rendering and avoiding a second assembled client
buffer.

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
