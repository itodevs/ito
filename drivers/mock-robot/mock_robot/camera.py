"""Video-file-backed camera input for the Mock Robot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import BinaryIO, Iterator


@dataclass(frozen=True)
class CameraSample:
    """A chunk read from the configured mock camera video file."""

    data: bytes
    offset: int
    timestamp_seconds: float


class VideoFileCamera:
    """Reads camera input from a local video file for later WebRTC publishing."""

    def __init__(self, path: str | Path, *, chunk_size: int = 64 * 1024, loop: bool = True) -> None:
        self.path = Path(path)
        self.chunk_size = chunk_size
        self.loop = loop
        self._file: BinaryIO | None = None

    @property
    def is_open(self) -> bool:
        return self._file is not None

    def validate(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"mock camera video file does not exist: {self.path}")
        if not self.path.is_file():
            raise ValueError(f"mock camera video path is not a file: {self.path}")
        if self.chunk_size <= 0:
            raise ValueError("mock camera chunk size must be > 0")

    def open(self) -> None:
        self.validate()
        self.close()
        self._file = self.path.open("rb")

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def samples(self) -> Iterator[CameraSample]:
        """Yield file chunks until EOF, looping when configured.

        TODO 23 will consume these bytes through WebRTC H.264 media transport.
        This class deliberately does not decode frames or implement a production
        replay mode in the reconstruction module.
        """

        if self._file is None:
            self.open()
        assert self._file is not None
        while True:
            offset = self._file.tell()
            data = self._file.read(self.chunk_size)
            if data:
                yield CameraSample(data=data, offset=offset, timestamp_seconds=monotonic())
                continue
            if not self.loop:
                break
            self._file.seek(0)

