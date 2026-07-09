"""Camera media publishing seam for Ito Droid WebRTC transport."""

from __future__ import annotations

import logging

from .ros_io import CameraFrame

LOGGER = logging.getLogger(__name__)


class CameraMediaPublisher:
    """Receives ROS camera frames for the driver-to-server WebRTC media path.

    TODO 23/26 will attach this seam to the real non-trickle WebRTC H.264
    transport. Keeping the boundary explicit lets the ROS camera consumer and
    session lifecycle be tested before the shared WebRTC signaling work lands.
    """

    def __init__(self) -> None:
        self.started_session_id: str | None = None
        self.frame_count = 0
        self.last_frame: CameraFrame | None = None

    @property
    def active(self) -> bool:
        return self.started_session_id is not None

    def start(self, session_id: str) -> None:
        self.started_session_id = session_id
        self.frame_count = 0
        self.last_frame = None

    def publish_frame(self, frame: CameraFrame) -> None:
        if not self.active:
            return
        self.frame_count += 1
        self.last_frame = frame
        LOGGER.debug("camera_media_frame bytes=%s encoding=%s", len(frame.data), frame.encoding)

    def stop(self) -> None:
        self.started_session_id = None

