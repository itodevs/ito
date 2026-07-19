# Future design considerations

These are candidate improvements within the one-pilot/one-robot product, not
accepted requirements.

## Reconstruction and capture

Evaluate onboard-capable systems such as MonoGS, MASt3R-SLAM, and Depth
Anything 3 against concrete robot hardware. Add only the camera calibration,
pose, stereo, RGB-D, or accelerator integration required by a selected model.
Keep reconstruction inside the Ito operational unit even when a native runtime
or tightly managed subprocess is needed.

## Visual age feedback

A robot adapter could compare source capture time with the latest scene update
acknowledged by the pilot. Define timing semantics for multi-frame
reconstruction before using this as a safety signal.

## Transport security

Deployment-specific TLS or private-network authentication may be needed. Any
security mechanism should protect the one Ito endpoint and, in external mode,
its one driver connection without introducing accounts, RBAC, discovery, or a
cloud control plane.

## Pilot experience

PCVR, hand tracking, gaze interaction, and richer robot-specific controls may
be evaluated after Pico 4 acceptance. The narrow adapter remains responsible
for concrete robot mapping and safety.

Multiple pilots, multiple robots, fleets, catalogs, and allocation remain out
of scope. They require a future product redesign, not dormant abstractions in
this codebase.
