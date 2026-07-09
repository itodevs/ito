"""Server-internal reconstruction processor interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence


CAPTURE_MODALITY_MONOCULAR_RGB = "monocularRgb"


@dataclass(frozen=True)
class ReconstructionFrame:
    """Decoded camera frame passed from server media ingress to reconstruction."""

    data: bytes
    timestamp_ms: int
    width: int
    height: int
    pixel_format: str = "rgb24"
    sequence: int | None = None


@dataclass(frozen=True)
class GaussianSplat:
    position: tuple[float, float, float]
    scale: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    color: tuple[int, int, int, int]


@dataclass(frozen=True)
class ProcessorSplatBatch:
    sequence: int
    splats: Sequence[GaussianSplat]


class ReconstructionProcessor(Protocol):
    """Common interface for algorithms under server/processors/."""

    capture_modality: str

    def start(self, session_id: str) -> None:
        ...

    def process_frame(self, frame: ReconstructionFrame) -> Iterable[ProcessorSplatBatch]:
        ...

    def reset(self) -> None:
        ...

    def close(self) -> None:
        ...
