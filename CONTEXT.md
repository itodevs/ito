# Ito domain language

**Pilot**
The person who perceives through and controls the configured robot.

**Pilot client**
The WebXR application served by Ito. It connects to the same Ito endpoint in
both deployment modes.

**Ito application / Ito app**
The single Python application that hosts the client, terminates the
pilot-facing protocol, runs reconstruction, and integrates one robot.

**Robot adapter**
The narrow internal boundary through which Ito starts/stops control and moves
pilot input and sensor frames. There is one adapter per Ito application.

**Local robot adapter**
The default in-process adapter. It receives pilot input and publishes sensor
frames using ordinary calls and memory.

**Remote robot adapter**
The optional Ito-side proxy for one lightweight remote robot driver.

**Remote robot driver**
The robot-local fallback component used when Ito runs externally. It forwards
sensors, accepts control targets, and retains robot-local safety guarantees.

**Control active / control paused / control stopped**
The direct lifecycle of pilot authority. These are connection and safety states,
not allocated resources.

**Pilot Input Snapshot**
A replaceable full-state pose and controller sample. Newest input wins.

**Robot-local safety**
Timeouts, rate limits, neutralization, emergency stop, and safe resumption that
continue to work without the pilot or external Ito connection.

**Reconstruction**
The live 3D representation produced from robot sensors while control is active.
Raw local frames stay onboard and enter reconstruction directly.

**Splat Batch / Splat Scene**
A binary incremental reconstruction update and the bounded client-owned scene
assembled from those updates.

Terms intentionally absent from the current product include robot catalog,
robot identity, acquisition, reservation, occupied robot, session authority,
and fleet state.
