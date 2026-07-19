# Pilot client

The WebXR client is served by the Ito Python application. Open Ito's root URL,
enter VR, connect to the same-origin `/ws` endpoint, and explicitly start
control. There is no robot browser or allocation step.

The client sends replaceable Pilot Input Snapshots and receives binary Splat
Batches. It pauses outgoing robot input while its menu is open or reconstruction
is stale. Robot and reconstruction placement is neither visible to the client
nor part of its workflow.

Run tests inside the Dev Container:

```bash
cd client && npm test
```
