# MVP vertical slice decisions

## 2026-06-12: Vendor the implementable submodules

`git submodule update --init --recursive` was attempted before implementation, but GitHub access is blocked in this environment with `CONNECT tunnel failed, response 403`. The `client` and `drivers/mock-robot` gitlinks therefore had no source to extend.

For a working, reviewable demo from this repository, this PR replaces those two unavailable gitlinks with independently buildable in-tree components. `drivers/ito-droid` remains an untouched submodule as required.

## 2026-06-12: Render PLY without Spark-specific parsing

The prompt requires `@sparkjsdev/spark`, but Spark primarily targets Gaussian splats rather than ordinary PLY meshes and its exact API may change. The MVP includes Spark as a pinned dependency, while rendering the processor's PLY through Three.js `PLYLoader`, which reliably produces a visible point cloud for standard PLY files.

## 2026-06-12: Use browser-created DataChannels

The client creates `control`, `status`, and `scene` channels before making its offer. This makes channel ownership and readiness deterministic across aiortc/browser connections. Services accept channels by label instead of creating potentially duplicated negotiated channels.

## 2026-06-12: Secure-context hosting

WebXR requires a secure context outside localhost. The root Compose setup serves HTTPS with a checked-in development certificate generated at container startup, rather than plain HTTP-only Nginx. Browsers must trust/accept the local certificate for the WSL address.

## 2026-06-12: Dependency installation and Compose verification unavailable here

The implementation pins runtime dependencies and includes component tests, but this environment blocks npm/GitHub downloads with HTTP 403 and does not provide Docker. I continued with syntax checks, dependency-free client tests, and static review; the PR's Compose smoke script is intended to run where Docker is available.

## 2026-06-12: Use host networking for the local WSL demo

Ordinary Docker bridge networking advertises container-only aiortc ICE host candidates and does not publish WebRTC's dynamic UDP ports, which would make the documented Windows-to-WSL direct connection fail. Compose therefore uses host networking for this local-only MVP. This allows aiortc to advertise WSL-host candidates and lets the processor reach the driver directly on loopback. A production deployment would need explicit ICE/STUN/TURN design, which is intentionally out of scope.
