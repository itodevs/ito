# Server Processors

This directory contains server-internal reconstruction algorithm modules.

These modules are part of the Ito Server codebase, not separately deployed Ito
programs.

All processors implement the interface in `base.py`: start a session, accept
decoded `ReconstructionFrame` values, and yield `ProcessorSplatBatch` values.
`null.py` is only an integration seam used before MASt3R-SLAM or MonoGS is
selected; it is not the v1 reconstruction algorithm.
