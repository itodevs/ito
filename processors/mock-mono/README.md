# Mock mono processor

The mock processor consumes the recorded driver's video through a direct
recv-only WebRTC peer. After the first frame, it streams a validated
Gaussian-splat PLY over the reliable `scene` DataChannel. The client feeds those
ordered chunks directly into SparkJS.

Run it through the root Compose application or set `SPLAT_FILE` and run:

```bash
uvicorn app.main:app --port 8002
```
