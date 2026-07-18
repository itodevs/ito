"""Null reconstruction processor used until the v1 monocular path is selected."""

from __future__ import annotations

from typing import Iterable

from .base import (
    CAPTURE_MODALITY_MONOCULAR_RGB,
    ProcessorSplatBatch,
    ReconstructionFrame,
)


class NullReconstructionProcessor:
    """Consumes frames and emits no splats.

    This is a local integration seam, not the selected v1 algorithm. It lets the
        application exercise sensor ingress, failure handling, and Splat Batch
    encoding without claiming MASt3R-SLAM or MonoGS have been selected.
    """

    capture_modality = CAPTURE_MODALITY_MONOCULAR_RGB

    def __init__(self) -> None:
        self.control_key: str | None = None
        self.frame_count = 0

    def start(self, control_key: str) -> None:
        self.control_key = control_key
        self.frame_count = 0

    def process_frame(self, frame: ReconstructionFrame) -> Iterable[ProcessorSplatBatch]:
        self.frame_count += 1
        return []

    def reset(self) -> None:
        self.frame_count = 0

    def close(self) -> None:
        self.control_key = None
