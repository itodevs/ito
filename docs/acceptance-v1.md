# Ito v1 acceptance

Automated acceptance currently proves:

- one Ito application serves the client and accepts the pilot connection;
- the client presents direct start/stop control with no browsing or allocation;
- a second simultaneous pilot is rejected;
- pilot disconnect invokes adapter stop;
- local sensor frames and pilot input cross the adapter boundary in-process;
- external mode connects one lightweight driver through the same pilot endpoint;
- control messages and live signaling contain no robot or allocation identity;
- Ito Droid retains local input timeout and neutralization behavior;
- Python and client unit/integration suites pass in the Dev Container.

Hardware acceptance still required:

- Pico 4 enters VR and negotiates both live channels;
- the selected reconstruction algorithm produces a usable scene;
- control loss, emergency stop, and safe resumption behave correctly on the
  physical robot;
- onboard latency/copy measurements meet the selected robot's limits.
