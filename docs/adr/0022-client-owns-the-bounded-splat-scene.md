# ADR 0022: The pilot client owns a bounded Splat Scene

## Decision

Ito sends incremental binary Splat Batches. The client applies them to its
rolling scene and evicts by age and budget. Visual-freshness timeout pauses pilot
input until fresh reconstruction returns.

The scene exists for current control, isn't a persistent world, and isn't shared
with another pilot.
