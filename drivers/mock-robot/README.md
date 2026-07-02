# Recorded robot driver

The recorded driver loops `VIDEO_FILE`, shares it through `MediaRelay`, and
accepts direct WebRTC client-control and processor-video peers. It logs accepted
WebXR poses and remains the final authority for disabled, disconnected, and
500 ms watchdog stops.

Run it through the root Compose application or set `VIDEO_FILE` and run:

```bash
uvicorn app.main:app --port 8001
```
