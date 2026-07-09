"""Session-scoped reconstruction runtime and failure isolation."""

from __future__ import annotations

from collections.abc import Callable
import logging

from server.processors.base import ReconstructionFrame, ReconstructionProcessor

from .splat import encode_splat_batch

LOGGER = logging.getLogger(__name__)


class ReconstructionSessionRuntime:
    """Owns one processor instance for one piloting session."""

    def __init__(
        self,
        session_id: str,
        processor: ReconstructionProcessor,
        *,
        send_splat_batch: Callable[[bytes], None],
        fail_session: Callable[[dict[str, str]], None],
    ) -> None:
        self.session_id = session_id
        self.processor = processor
        self.send_splat_batch = send_splat_batch
        self.fail_session = fail_session
        self.failed = False

    def start(self) -> None:
        self.processor.start(self.session_id)

    def process_frame(self, frame: ReconstructionFrame) -> None:
        if self.failed:
            return
        try:
            for batch in self.processor.process_frame(frame):
                self.send_splat_batch(encode_splat_batch(batch))
        except Exception:
            LOGGER.exception("Reconstruction failed for session %s", self.session_id)
            self.failed = True
            self.fail_session({"code": "session.ended.reconstruction_failed"})

    def close(self) -> None:
        try:
            self.processor.close()
        except Exception:
            LOGGER.exception("Reconstruction processor close failed for session %s", self.session_id)
