"""Validation and bounded chunk iteration for a Gaussian-splat PLY source."""

from collections.abc import Iterator
from pathlib import Path

CHUNK_SIZE = 12_000
REQUIRED_GAUSSIAN_PROPERTIES = (
    b"property float x",
    b"property float y",
    b"property float z",
    b"property float scale_0",
    b"property float scale_1",
    b"property float scale_2",
    b"property float rot_0",
    b"property float rot_1",
    b"property float rot_2",
    b"property float rot_3",
    b"property float opacity",
    b"property float f_dc_0",
)


def load_splat_ply(path: str) -> bytes:
    """Read a PLY and reject ordinary point clouds that lack Gaussian attributes."""
    data = Path(path).read_bytes()
    header_end = data.find(b"end_header\n", 0, 65_536)
    if not data.startswith(b"ply\n") or header_end < 0:
        raise ValueError(f"{path} is not a valid PLY file")

    header = data[:header_end]
    missing = [name.decode() for name in REQUIRED_GAUSSIAN_PROPERTIES if name not in header]
    if missing:
        raise ValueError(f"{path} is not a Gaussian-splat PLY; missing {', '.join(missing)}")
    return data


def iter_splat_chunks(data: bytes, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    """Yield sequential DataChannel-sized views without constructing a chunk list."""
    for offset in range(0, len(data), chunk_size):
        yield data[offset:offset + chunk_size]
