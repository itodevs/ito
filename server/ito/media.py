"""Camera media decoding into reconstruction frames."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from server.processors.base import ReconstructionFrame


@dataclass(frozen=True)
class EncodedCameraSample:
    data: bytes
    timestamp_ms: int


class H264CameraDecoder:
    """Decode H.264 samples to RGB reconstruction frames using PyAV when present."""

    def __init__(self) -> None:
        try:
            import av
        except ImportError as exc:  # pragma: no cover - depends on optional media stack
            raise RuntimeError("PyAV is required for H.264 camera decoding") from exc
        self._av = av
        self._codec = av.CodecContext.create("h264", "r")
        self._sequence = 0

    def decode(self, sample: EncodedCameraSample) -> Iterable[ReconstructionFrame]:
        packet = self._av.Packet(sample.data)
        packet.pts = sample.timestamp_ms
        packet.time_base = Fraction(1, 1000)
        for decoded in self._codec.decode(packet):
            rgb = decoded.to_rgb()
            self._sequence += 1
            yield ReconstructionFrame(
                data=bytes(rgb.planes[0]),
                timestamp_ms=sample.timestamp_ms,
                width=rgb.width,
                height=rgb.height,
                pixel_format="rgb24",
                sequence=self._sequence,
            )
