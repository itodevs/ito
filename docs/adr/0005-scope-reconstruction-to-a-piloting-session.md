# Scope reconstruction to a piloting session

The Ito Server creates reconstruction state for a piloting session and discards it when the session ends. Reconstructions are never shared across sessions, persisted as maps, or maintained for unoccupied robots. They exist to provide a responsive pilot view despite network and robot-motion latency, not to make Ito a mapping system.

During temporary connection recovery, the Ito Server should retain reconstruction state only to the extent the selected reconstruction algorithm can safely continue after transport or camera discontinuity. Some algorithms may not tolerate the camera effectively "jumping" after media reconnection. In that case, the server may reset reconstruction state within the same piloting session rather than ending the session, as long as fresh reconstruction can resume.

The first reconstruction spike should observe each candidate algorithm's behavior after short media interruptions and resumed feed from a slightly changed pose. Built-in recovery is a selection benefit, but Ito does not make it a hard algorithm responsibility for v1 because server-side reconstruction reset remains an acceptable recovery mechanism within the same session.

If reconstruction fails, the failure applies to that piloting session. The Ito Server should stop the affected session rather than crash the whole server.

Reconstruction should be testable against the same feed boundary used by real sessions. Unit tests may inject decoded frames or an abstract feed directly. Integration tests may use a Mock Robot that supplies a video-file-backed Sensor Feed over the real WebRTC H.264 media path, exercising transport and decoding without adding a production replay mode to the reconstruction module.

The Mock Robot should behave like a robot driver in every relevant Ito interaction. If it runs and reports to the Ito Server, it appears in the Robot Catalog like any other robot. It accepts pilot input and logs received Pilot Input Snapshots to stdout, but does not maintain an internal fake robot pose unless a later test needs that state for a concrete assertion.
