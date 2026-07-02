# Future Design Considerations

These are potential expansions, not accepted requirements or architecture.

## End-to-end visual freshness feedback

A robot driver could attach a timestamp from its own monotonic clock to each captured camera frame. The Ito Server would preserve source timing through reconstruction updates, and the client would echo the timestamp associated with the latest splats actually shown to the pilot alongside pilot input. Because the timestamp originated at the robot, the driver could compare the echoed value with its current clock and optionally reject control when displayed visual information exceeds a robot-specific safety threshold.

Before implementing this, define how one reconstruction update represents timing when it incorporates multiple camera frames or updates only part of the scene.

## Authentication and authorization

Ito v1 does not authenticate robot drivers or pilots at the application layer. A future security design should treat these as separate responsibilities:

- authenticate each robot driver so another machine cannot claim its catalog identity;
- authenticate pilots and use role-based access control to limit which robots they may see or pilot;
- protect transport integrity and confidentiality against interception or modification;
- authenticate piloting-session resumption so only the original pilot can recover control.

RBAC alone does not prevent a fake robot driver or a man-in-the-middle attack. Candidate mechanisms include provisioned driver keys, mutual TLS, and trusted network identity, but no mechanism has been selected.

## Multiple capture modalities

Robot drivers may eventually provide monocular RGB, calibrated stereo RGB, RGB-D, or other sensor configurations. The Ito Server should select reconstruction suited to the available Capture Modality rather than treating v1's monocular algorithm as universal. For example, a learned monocular prior such as MASt3R-SLAM is unnecessary when calibrated stereo or measured depth already provides geometric information. V1 implements only the available USB webcam's monocular path and should not build the general selection system yet.

The reconstruction spike should determine the minimum metadata required for each supported algorithm. Camera intrinsics, mounting extrinsics, capture timestamps, and robot-reported camera poses are candidates, not baseline protocol requirements; omit anything the selected algorithm does not demonstrably use.

V1 sends monocular camera input as a WebRTC media track. Future stereo can use multiple synchronized media tracks or a packed stereo video representation. Future RGB-D can use an RGB media track plus a depth representation if the selected reconstruction algorithm benefits from it. Point clouds and other non-image geometry are not a natural media-track fit; they should likely use a binary data channel or another explicit geometry transport. The transport should be selected per Capture Modality rather than assuming every sensor type is a single video track.

V1 requires H.264 for the robot camera media track. Future versions may add camera codec negotiation, VP8/VP9/AV1, hardware-specific codec preferences, or direct ingest paths if target robots or reconstruction pipelines justify the complexity.

V1 does not define required camera resolution or frame rate. Future algorithm-specific requirements may define recommended or required capture settings per Capture Modality.

V1 leaves WebRTC media bitrate, congestion behavior, and related camera transport tuning to defaults. Future versions may expose media transport settings if reconstruction quality or network behavior requires explicit control.

## PCVR and desktop WebXR

Ito v1 targets standalone WebXR on Pico 4's built-in browser. PCVR through systems such as Virtual Desktop would be useful for higher rendering budgets and development ergonomics, but desktop WebXR support is not treated as reliable enough to be a v1 acceptance path.

## More physical VR interaction

Ito v1 uses controller-ray interaction for VR UI. Future versions may explore hand tracking, gaze interaction, direct-touch panels, or other more physical VR interaction models, but those are not required to prove the v1 reconstruction and teleoperation loop.

## Robot-type control conventions

Robots of the same Robot Type should generally feel similar to pilot. For example, a Car is likely to rely more on joystick and trigger controls than full-body pose, while humanoid types are likely to rely more on body mapping. Ito may eventually define explicit Control Conventions per Robot Type, but v1 does not introduce a formal control-profile or capability system. The robot driver remains responsible for concrete mapping and robot-specific controls.

## Persistent robot catalog

Ito v1 keeps the Robot Catalog in server memory and builds it from robot-driver reports. A future version may add a persistent robot registry or configured inventory so unavailable robots remain visible across server restarts, but v1 does not require that.

## Themed UI language

Ito v1 externalizes pilot-facing UI text into JSON resource files for future localization. The same resource mechanism could later support selected language styles or themes, such as Ghost in the Shell, Matrix, or cyberpunk-inspired terminology, without changing UI components.
