# ADR 0019: One application, one pilot, one robot

## Decision

Ito is one Python application for one pilot and one configured robot. The
application hosts the WebXR client, terminates its control and live-data paths,
runs reconstruction, and controls the robot through one narrow adapter.

The default adapter is local and in-process. An optional remote adapter connects
one lightweight robot driver when the robot cannot run Ito onboard. Placement is
configuration and doesn't alter the pilot-facing protocol.

Multi-user support, multiple robots per application, discovery, catalogs,
browsing, stable robot identities, allocation, reservations, availability
lists, fleet heartbeats, and distributed session coordination are explicitly
out of scope. If those become real product requirements, they require a new
architecture rather than dormant compatibility layers.

## Consequences

Ito has fewer processes, network links, messages, identifiers, states, and
deployment units. Breaking the previous prototype protocol is intentional.
