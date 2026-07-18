# Reconstruction processors

These modules run inside the Ito application boundary. A processor starts when
control starts, accepts `ReconstructionFrame` values directly from local sensor
ingress or decoded remote media, and yields binary-ready `ProcessorSplatBatch`
values.

`null.py` is only an integration seam; it is not the selected reconstruction
algorithm. Native libraries, GPU runtimes, or a tightly managed model subprocess
may implement this interface without becoming another deployed Ito service.
