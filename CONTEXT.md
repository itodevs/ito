# Ito

Ito is an immersive teleoperation system for people who directly pilot robots.

## Language

**Pilot**:
The person who perceives through and controls a robot in real time through Ito.
_Avoid_: User, operator

**Robot**:
The physical or simulated embodied machine controlled by a pilot.
_Avoid_: Device

**Robot Type**:
A coarse Ito-known embodiment category used to orient the pilot to the robot they are about to inhabit, including likely control style. Current types are Mecha, Android Robot, Droid, Drone, Car, and Plane.
_Avoid_: Hardware model, driver type, capture modality, capability contract

**Control Convention**:
The expected control style for a Robot Type. Robots of the same type should feel similar to pilot, but each robot driver remains responsible for its concrete control mapping and any robot-specific controls.
_Avoid_: Control profile, capability contract, universal mapping

**Mecha**:
A large humanoid robot.
_Avoid_: Android Robot, Droid

**Android Robot**:
A human-sized humanoid robot. Use the full term when ambiguity with the Android operating system is possible.
_Avoid_: Android device, Droid

**Droid**:
A small humanoid robot.
_Avoid_: Android Robot, device

**Drone**:
A quadcopter or similar flying robot that can hover.
_Avoid_: Plane

**Car**:
A robot on three or more wheels.
_Avoid_: Rover

**Plane**:
A winged aircraft that relies on forward momentum to stay at altitude.
_Avoid_: Drone

**Ito Droid**:
Ito's physical reference robot family for validating the complete piloting experience.
_Avoid_: Ito platform, required robot architecture

**Robot Catalog**:
The server-memory set of robots known to Ito from robot-driver reports and offered to a pilot for selection.
_Avoid_: Persistent registry, static robot inventory

**Robot Identity**:
The stable machine-readable identity a robot driver reports for catalog and session bookkeeping. In v1 it is not proof of authenticity.
_Avoid_: Robot name, credential, authentication

**Session Identity**:
The server-generated identity for a piloting session.
_Avoid_: Client session token, WebRTC connection ID

**Driver Status Report**:
A repeated robot-driver-to-server report that refreshes the server's in-memory Robot Catalog entry for that robot.
_Avoid_: Robot authentication, proof of identity

**Driver Status Watchdog**:
The server-owned duration after which a robot becomes Unavailable if its driver has not sent fresh status over its control connection.
_Avoid_: Pilot input timeout, session cleanup timeout, control-loss timeout

**Robot Status**:
Current availability/session state used to present a catalog entry. V1 states are Available, Occupied, and Unavailable. Available and Unavailable come from driver availability plus server connectivity; Occupied is assigned by the Ito Server when it reserves or allocates the robot for a pilot.
_Avoid_: Catalog metadata

**Occupied Robot**:
A robot that the Ito Server has reserved for an in-progress acquisition or allocated to a piloting session.
_Avoid_: Connected robot, busy robot

**Robot Driver**:
The robot-side Ito component that connects a robot to Ito, reports robot availability, translates pilot input into robot commands, and forwards sensor feeds needed by Ito.
_Avoid_: Robot app, server driver

**Ito Protocol**:
The shared message and media contract between the Pilot Client, Ito Server, and Robot Driver.
_Avoid_: ROS API, WebRTC glue, implementation class model

**Ito Protocol Version**:
The exact Ito Protocol version identifier advertised by Ito programs. V1 requires an exact version match.
_Avoid_: API version, feature negotiation

**Piloting Session**:
A bounded, exclusive period in which the Ito Server allocates one pilot control authority over one robot. It can survive temporary loss or replacement of its network connection.
_Avoid_: WebRTC session, peer session

**Session Authority**:
The responsibility for deciding whether a pilot may acquire a robot and for serializing competing acquisition attempts. The Ito Server is the session authority and may reserve a robot during acquisition to prevent races; the robot driver remains the control safety authority.
_Avoid_: Control safety authority, robot driver authority

**Driver-Terminated Session**:
A piloting session ended by the robot driver because the driver or robot can no longer satisfy the session's required behavior. It is reserved for non-recoverable driver or robot conditions, not ordinary transient control loss.
_Avoid_: Disconnect, control loss

**Session Termination Reason**:
A driver- or server-provided display value explaining why a session ended. It may be a localization resource key or free text.
_Avoid_: Log line, robot status

**Display Reason**:
A displayable reason value supplied across Ito IPC, represented as either a localization resource key or free text fallback.
_Avoid_: Exception, log message, internal error

**Request Timeout**:
The configurable duration after which an Ito WebSocket request expecting a response is treated as failed if no correlated response arrives.
_Avoid_: Pilot input timeout, visual freshness timeout, session cleanup timeout

**Pilot Input**:
Robot-independent, time-varying data produced by the pilot, including tracked body poses and controller input.
_Avoid_: Robot command, control message

**Pilot Input Snapshot**:
A complete current-state sample of pilot input, including relevant pose, controller axes, and button state at that moment. It replaces earlier snapshots rather than depending on delivery of every prior message.
_Avoid_: Input delta, command event

**Pilot Input Rate**:
The frequency at which the Pilot Client sends Pilot Input Snapshots during an active session. V1 defaults to 60 Hz.
_Avoid_: Render frame rate, pilot-input timeout

**Driver Control Tick**:
One iteration of a robot driver's control loop. The driver uses the newest available Pilot Input Snapshot at each tick and discards older queued snapshots. Ito Droid v1 defaults to 60 Hz.
_Avoid_: Pilot input rate, render frame

**Pilot Input Timeout**:
The robot-driver-owned duration after which missing fresh pilot input causes control loss. For v1 Ito Droid, this defaults to 2 seconds.
_Avoid_: Visual freshness timeout, network timeout

**Menu Pause**:
A Pilot Client state in which an in-VR menu is open and robot-directed pilot input is withheld while UI interaction remains active.
_Avoid_: Visual freshness timeout, session end

**Pilot Frame**:
The piloting-session-relative coordinate frame used to interpret pilot input. For v1 camera-pan control, headset yaw at session start defines zero yaw.
_Avoid_: World frame, headset absolute pose

**Pilot Client**:
The WebXR application used by the pilot to perceive reconstruction and produce pilot input.
_Avoid_: Viewer, dashboard

**Robot Command**:
A robot-specific target or action derived from pilot input.
_Avoid_: Pilot input

**Control Mapping**:
The robot-driver-owned translation from pilot input in the Pilot Frame into robot commands, including robot-specific limits, smoothing, and rate limits.
_Avoid_: Control convention, universal control scheme, raw pose forwarding

**Sensor Feed**:
A live robot-provided observation stream, such as a camera feed, that Ito consumes for reconstruction or direct view. Producing and configuring the feed is outside Ito's responsibility.
_Avoid_: Ito camera, reconstruction output

**Mock Robot**:
A test double that behaves like a robot driver in every relevant Ito interaction, including reporting to the Robot Catalog, providing a Sensor Feed from a video file, and accepting pilot input.
_Avoid_: Hidden test mode, replay mode

**Reconstruction**:
A session-scoped, evolving three-dimensional representation derived from robot sensor input. It gives the pilot a locally responsive viewpoint despite robot-motion and network latency.
_Avoid_: Persistent map, processed view, processor output

**Reconstruction Algorithm**:
A server-internal method for turning a compatible Capture Modality into Splat Batches for a piloting session.
_Avoid_: Deployed processor, visual processor, client renderer

**Reconstruction Failure**:
A failure of the session-scoped reconstruction pipeline that prevents Ito from producing fresh Splat Batches for that session. It should stop the affected piloting session without crashing the Ito Server.
_Avoid_: Server crash, robot failure

**Capture Modality**:
The form of visual observations available for reconstruction, such as monocular RGB, calibrated stereo RGB, or RGB-D.
_Avoid_: Camera model, reconstruction algorithm

**Splat Scene**:
The client-owned reconstruction presented to the pilot as a rolling collection of Gaussian splats.
_Avoid_: Splat file, point cloud, processor output

**Splat Batch**:
A unit of newly reconstructed splat data that the client receives, adds to its Splat Scene, and later evicts as a unit.
_Avoid_: Splat file, scene snapshot

**Splat Budget**:
The maximum number of splats a client retains in its Splat Scene for its performance constraints.
_Avoid_: Frame-rate limit, level of detail

**Splat Lifetime**:
The maximum age for which a client retains a Splat Batch in its Splat Scene.
_Avoid_: Session lifetime, visual-freshness timeout

**Direct View**:
An optional pilot view that presents robot camera footage without reconstruction.
_Avoid_: Raw mode, visual processor

**Visual Freshness**:
The recency of reconstruction output successfully applied by the Pilot Client. In v1 this is measured as time since the last Splat Batch completed the client's normal receive-and-apply path, not as a claim about exactly what geometry is currently in the pilot's view.
_Avoid_: Render frame rate, message latency, scene quality

**Visual Freshness Timeout**:
The client-side duration after which missing fresh reconstruction output causes the Pilot Client to pause controls and withhold pilot input. V1 defaults this timeout to 2 seconds.
_Avoid_: Splat lifetime, network timeout

**Control Loss**:
The condition in which sufficiently fresh, valid pilot input is no longer available during active control. It may be recoverable during a recovery period and is distinct from a driver-terminated session.
_Avoid_: Disconnect, timeout

**Control-Loss Response**:
The robot-specific behavior used to keep a robot safe and stable after control loss, such as braking, hovering, balancing, or descending.
_Avoid_: Safe stop, universal failsafe

**Control Resumption**:
The transition from control loss back to active control after fresh pilot input resumes. The robot driver owns this transition and must prevent sudden dangerous motion while reconciling differences between pilot pose and robot pose.
_Avoid_: Reconnect, snap back

**Control Safety Authority**:
The responsibility for deciding how robot control behaves when inputs or conditions are unsafe. The robot driver is primary; the pilot client is secondary by deciding whether to continue sending pilot input; the Ito Server does not make robot-control decisions.
_Avoid_: Server safety policy, central control authority

**Recovery Period**:
The driver-defined interval after connection loss during which a piloting session remains occupied and can be resumed by the same pilot.
_Avoid_: Connection timeout, control-loss response

**Session Cleanup Timeout**:
The server-owned duration after which Ito removes stale session state when the responsible endpoint is gone. It is bookkeeping for resource cleanup, not a robot-safety mechanism.
_Avoid_: Control-loss timeout, pilot-input timeout

**Control Authority**:
The exclusive permission conferred by a piloting session for one pilot's input to affect its robot. It has the same lifecycle as the piloting session and is allocated by the Ito Server.
_Avoid_: Connection, enable flag
