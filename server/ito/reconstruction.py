"""Control-lifecycle reconstruction runtime and failure isolation."""

from __future__ import annotations

from collections.abc import Callable
import logging

from server.processors.base import ReconstructionFrame, ReconstructionProcessor

from .splat import encode_splat_batch

LOGGER = logging.getLogger(__name__)


class ReconstructionRuntime:
    """Owns the processor while control is active."""

    def __init__(
        self,
        processor: ReconstructionProcessor,
        *,
        send_splat_batch: Callable[[bytes], None],
        fail_control: Callable[[dict[str, str]], None],
    ) -> None:
        self.processor = processor
        self.send_splat_batch = send_splat_batch
        self.fail_control = fail_control
        self.failed = False

    def start(self) -> None:
        self.processor.start()

    def process_frame(self, frame: ReconstructionFrame) -> None:
        if self.failed:
            return
        try:
            for batch in self.processor.process_frame(frame):
                self.send_splat_batch(encode_splat_batch(batch))
        except Exception:
            LOGGER.exception("Reconstruction failed while control is active")
            self.failed = True
            self.fail_control({"code": "control.stopped.reconstruction_failed"})

    def close(self) -> None:
        try:
            self.processor.close()
        except Exception:
            LOGGER.exception("Reconstruction processor close failed")
