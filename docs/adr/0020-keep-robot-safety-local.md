# ADR 0020: Keep robot safety local

## Decision

Pilot-input timeout, command limits, neutralization, emergency stop, and safe
resumption live in or next to the local adapter. In external mode the lightweight
driver retains the same guarantees on the robot.

Loss of pilot input or any external connection must produce a safe local
response without waiting for another machine. Ito may pause or stop control, but
it isn't a remote prerequisite for the robot's safety behavior.
