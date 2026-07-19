"""Camera media publishing seam for Ito Droid WebRTC transport."""

from __future__ import annotations

import logging
from typing import Any

from .ros_io import CameraFrame
from .webrtc import CameraMediaWebRtcPublisher

LOGGER = logging.getLogger(__name__)


class CameraMediaPublisher:
    """Receives ROS camera frames for the driver-to-server WebRTC media path.

    The newest raw ROS frame enters the WebRTC video track in memory. The
    transport then encodes it for the physically necessary robot-to-Ito hop.
    """

    def __init__(self, transport: Any | None = None) -> None:
        self.active = False
        self.frame_count = 0
        self.last_frame: CameraFrame | None = None
        self._transport = transport

    def start(self) -> None:
        self.active = True
        self.frame_count = 0
        self.last_frame = None

    def publish_frame(self, frame: CameraFrame) -> None:
        if not self.active:
            return
        self.frame_count += 1
        self.last_frame = frame
        if self._transport is not None:
            self._transport.publish_frame(frame)
        LOGGER.debug("camera_media_frame bytes=%s encoding=%s", len(frame.data), frame.encoding)

    async def create_offer(self) -> str:
        if self._transport is None:
            self._transport = CameraMediaWebRtcPublisher()
        if self.last_frame is not None:
            self._transport.publish_frame(self.last_frame)
        return await self._transport.create_offer()

    async def accept_answer(self, *, sdp: str) -> None:
        if self._transport is None:
            raise RuntimeError("camera media has no active offer")
        await self._transport.accept_answer(sdp=sdp)

    async def close(self) -> None:
        if self._transport is not None:
            await self._transport.close()

    def stop(self) -> None:
        self.active = False
