# Recorded robot driver

Set `VIDEO_FILE` to a seekable video and run `uvicorn app.main:app --port 8001`.
The service loops the file, relays it to every direct WebRTC subscriber, and
owns the final 500 ms control watchdog.
