from pathlib import Path

CHUNK_SIZE = 12_000

def load_ply(path: str) -> bytes:
    data = Path(path).read_bytes()
    if not data.startswith(b"ply\n") or b"end_header\n" not in data[:65536]:
        raise ValueError(f"{path} is not a valid PLY file")
    return data

def split_scene(data: bytes, chunk_size: int = CHUNK_SIZE) -> list[bytes]:
    return [data[offset:offset + chunk_size] for offset in range(0, len(data), chunk_size)]
