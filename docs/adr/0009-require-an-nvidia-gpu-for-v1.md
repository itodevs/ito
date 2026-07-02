# Require an NVIDIA GPU for v1

Ito v1 targets an x86_64 server with an NVIDIA GPU and runs in one container with NVIDIA Container Runtime access. Live neural reconstruction is the primary technical risk, so v1 will use the CUDA ecosystem directly rather than dilute that work with a CPU fallback or hardware-portability layer. Broader accelerator support can follow evidence of need.
