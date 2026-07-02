# Use a monolithic Ito server

Ito has one central server program, process, and IPC API. It maintains the Robot Catalog and current Robot Status from robot-driver status reports, acts as session authority for piloting-session allocation and recovery, and performs visual reconstruction. Robot drivers run on their robots rather than as server-side services. The Pilot Client is a static website that may be hosted separately, such as by nginx; static web hosting is not part of Ito IPC. Remote robot drivers should not require inbound reachability, and Ito's server-side behavior belongs to one cohesive application.

Decoding received robot camera media into frames for reconstruction is inside the monolithic Ito Server boundary. The server may use internal libraries or subprocess-style tooling inside its container, but v1 does not introduce a separate media ingestion or decoding service. Reconstruction may run in-process or as a subprocess inside the same server container; the selected path must avoid large unnecessary copies between decode, reconstruction, and Splat Batch output, and the reconstruction spike should measure that overhead.

Reconstruction algorithm implementations live under `server/processors/` as server-internal modules. They share a server-internal interface, but individual implementations may accept different Capture Modalities such as monocular RGB, calibrated stereo RGB, or RGB-D.

Reconstruction failure is session-scoped. The desired behavior is to stop the affected piloting session while keeping the Ito Server alive, preserving the path toward future multi-robot and multi-pilot operation. This makes failure isolation a requirement even though reconstruction remains inside the monolithic server boundary.

The server is deployed as a Docker container. Runtime settings are supplied through environment variables in Docker Compose rather than through separate configuration services or mutable in-app configuration.
