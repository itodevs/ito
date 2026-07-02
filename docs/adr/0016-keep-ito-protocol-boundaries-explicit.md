# Keep Ito Protocol boundaries explicit

Ito v1 is implemented as three cooperating programs: the Pilot Client, the Ito Server, and a Robot Driver. Their shared boundary is the Ito Protocol: message contracts, media paths, session lifecycle semantics, and displayable status/reason values. Technology-specific code such as ROS integration, WebXR input/rendering, WebRTC peer management, Spark.JS insertion, and reconstruction algorithm wrappers should sit behind that boundary rather than becoming the domain model itself.

This keeps ROS specific to the Ito Droid driver, keeps browser/WebXR concerns out of the robot driver, and keeps server/session logic independent from any one robot or reconstruction algorithm. The goal is not heavy layering; it is one generic protocol interface between each program so future robot types, driver languages, capture modalities, and reconstruction algorithms can be swapped without rewriting the whole teleoperation loop.

For v1, those seams are documented in `docs/protocol.md` and manually implemented in Python for the Ito Server and robot drivers, and plain JavaScript for the Pilot Client. V1 does not use TypeScript or generated protocol bindings.

V1 uses exact Ito Protocol Version matching with the identifier `ito.v1`. It fails fast on version mismatch.
