# Ito Server

The Ito Server coordinates Ito's shared server-side state and reconstruction.

## Dependencies

The server uses `msgpack` and `websockets` for the Ito control plane. WebRTC and
H.264 camera decoding use `aiortc` and `av`/PyAV.

Install local Python dependencies from the repository root:

```sh
python -m pip install -r server/requirements.txt
```

Run tests from the repository root:

```sh
pytest -q
```

Docker Compose commands for running the Ito Server with the static Pilot Client
and optional Mock Robot are documented in `../docs/local-v1.md`.
