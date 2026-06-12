# Mock mono processor

Set `SPLAT_FILE` to a valid PLY and run `uvicorn app.main:app --port 8002`.
The processor directly subscribes to the recorded driver's video, reports
freshness, and sends the mounted scene to its client after the first frame.
