# Robot drivers own control translation

Ito clients send robot-independent pilot input. Each robot driver translates that input into robot-specific commands, applies robot-specific constraints, and owns the response to control loss and control resumption. The pilot client may decide to withhold pilot input when local checks fail or UI state requires it, and may resume sending input when those checks pass again or the UI state closes, but the Ito Server does not make robot-control decisions. Control-loss and resumption behavior is robot-specific: stopping is not safe or feasible for every robot, and snapping directly back to the pilot's pose can be dangerous. This keeps embodiment and safety-policy knowledge out of the server and avoids inserting a required control-processing service into the latency- and safety-critical path.

Pilot input is sent as repeated full-state snapshots rather than deltas. This lets the driver use the newest available state and tolerate dropped stale samples. V1 defaults to sending snapshots at 60 Hz, configurable by the Pilot Client. The robot driver runs its own control loop and uses only the newest available snapshot on each control tick, discarding older queued snapshots. Ito Droid v1 defaults this control tick rate to 60 Hz, configurable by driver environment variable.

Each driver also owns its pilot-input timeout. Ito Droid v1 defaults this timeout to 2 seconds, but other robot types may need different thresholds and responses. Any client-side reason for withholding robot-directed pilot input, including visual freshness timeout or Menu Pause, reaches the driver as missing pilot input and uses the driver's normal control-loss behavior.

For Ito Droid v1, safe control resumption means ramping the allowed camera-pan servo correction velocity from a low value back to normal over a configurable duration, rather than snapping immediately to the current pilot yaw.

Ito Droid v1's recoverable control-loss response holds the camera-pan servo at its last commanded position. Returning the servo toward neutral happens on session end, not during recoverable control loss.
