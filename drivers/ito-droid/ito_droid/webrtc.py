"""Driver-side WebRTC helpers for Ito Droid live paths."""

from __future__ import annotations

import asyncio
from fractions import Fraction
import logging
from typing import Any, Callable, Mapping

from server.ito.webrtc import decode_pilot_input_snapshot

from .ros_io import CameraFrame

LOGGER = logging.getLogger(__name__)


class PilotInputDataChannelReceiver:
    """Attach a WebRTC data channel to an existing Pilot Input Snapshot sink."""

    def __init__(self, receive_snapshot: Callable[[Mapping[str, Any]], None]) -> None:
        self.receive_snapshot = receive_snapshot

    def attach(self, data_channel: Any) -> None:
        @data_channel.on("message")
        def on_message(message: str | bytes) -> None:
            try:
                snapshot = decode_pilot_input_snapshot(message)
            except ValueError as exc:
                LOGGER.warning("Ignoring invalid Pilot Input Snapshot: %s", exc)
                return
            self.receive_snapshot(snapshot)


class PilotInputWebRtcReceiver:
    """Accept the pilot data-channel offer and feed the local controller."""

    def __init__(self, receive_snapshot: Callable[[Mapping[str, Any]], None]) -> None:
        try:
            from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("aiortc is required for Ito Droid pilot input") from exc
        self._configuration_type = RTCConfiguration
        self._peer_connection_type = RTCPeerConnection
        self._session_description_type = RTCSessionDescription
        self._receiver = PilotInputDataChannelReceiver(receive_snapshot)
        self._peer_connection: Any | None = None

    async def accept_offer(self, *, sdp: str) -> str:
        await self.close()
        pc = self._peer_connection_type(configuration=self._configuration_type(iceServers=[]))
        self._peer_connection = pc

        @pc.on("datachannel")
        def on_data_channel(channel: Any) -> None:
            self._receiver.attach(channel)

        await pc.setRemoteDescription(self._session_description_type(sdp=sdp, type="offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        await _wait_for_ice_gathering_complete(pc)
        return pc.localDescription.sdp

    async def close(self) -> None:
        pc = self._peer_connection
        self._peer_connection = None
        if pc is not None:
            await pc.close()


class CameraMediaWebRtcPublisher:
    """Publish newest ROS camera frames to Ito as one WebRTC video track."""

    def __init__(self) -> None:
        try:
            from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
            from aiortc import VideoStreamTrack
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("aiortc is required for Ito Droid camera media") from exc

        class RosCameraTrack(VideoStreamTrack):
            def __init__(self) -> None:
                super().__init__()
                self.frames: asyncio.Queue[CameraFrame] = asyncio.Queue(maxsize=1)

            def publish(self, frame: CameraFrame) -> None:
                if self.frames.full():
                    self.frames.get_nowait()
                self.frames.put_nowait(frame)

            async def recv(self) -> Any:
                frame = await self.frames.get()
                return _video_frame(frame)

        self._configuration_type = RTCConfiguration
        self._peer_connection_type = RTCPeerConnection
        self._session_description_type = RTCSessionDescription
        self._track = RosCameraTrack()
        self._peer_connection: Any | None = None

    def publish_frame(self, frame: CameraFrame) -> None:
        self._track.publish(frame)

    async def create_offer(self) -> str:
        await self.close()
        pc = self._peer_connection_type(configuration=self._configuration_type(iceServers=[]))
        self._peer_connection = pc
        pc.addTrack(self._track)
        _prefer_h264(pc)
        await pc.setLocalDescription(await pc.createOffer())
        await _wait_for_ice_gathering_complete(pc)
        return pc.localDescription.sdp

    async def accept_answer(self, *, sdp: str) -> None:
        if self._peer_connection is None:
            raise RuntimeError("no camera-media offer is active")
        await self._peer_connection.setRemoteDescription(
            self._session_description_type(sdp=sdp, type="answer")
        )

    async def close(self) -> None:
        pc = self._peer_connection
        self._peer_connection = None
        if pc is not None:
            await pc.close()


def _video_frame(frame: CameraFrame) -> Any:
    try:
        from av import VideoFrame
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("PyAV is required for Ito Droid camera media") from exc
    if frame.width is None or frame.height is None:
        raise ValueError("ROS camera frames require width and height")
    formats = {
        "rgb8": ("rgb24", 3),
        "bgr8": ("bgr24", 3),
        "rgba8": ("rgba", 4),
        "bgra8": ("bgra", 4),
        "mono8": ("gray", 1),
    }
    try:
        pixel_format, bytes_per_pixel = formats[frame.encoding or ""]
    except KeyError as exc:
        raise ValueError(f"unsupported ROS camera encoding: {frame.encoding}") from exc
    video_frame = VideoFrame(frame.width, frame.height, pixel_format)
    plane = video_frame.planes[0]
    row_size = frame.width * bytes_per_pixel
    if len(frame.data) != row_size * frame.height:
        raise ValueError("ROS camera frame size does not match its dimensions")
    if plane.line_size == row_size:
        packed = frame.data
    else:
        padding = b"\0" * (plane.line_size - row_size)
        packed = b"".join(
            frame.data[offset : offset + row_size] + padding
            for offset in range(0, len(frame.data), row_size)
        )
    plane.update(packed)
    video_frame.pts = int(frame.received_at_seconds * 90_000)
    video_frame.time_base = Fraction(1, 90_000)
    return video_frame


def _prefer_h264(peer_connection: Any) -> None:
    from aiortc import RTCRtpSender

    codecs = [
        codec
        for codec in RTCRtpSender.getCapabilities("video").codecs
        if codec.mimeType.lower() == "video/h264"
    ]
    for transceiver in peer_connection.getTransceivers():
        if transceiver.kind == "video" and codecs:
            transceiver.setCodecPreferences(codecs)


async def _wait_for_ice_gathering_complete(peer_connection: Any) -> None:
    if getattr(peer_connection, "iceGatheringState", None) == "complete":
        return
    complete = asyncio.Event()

    @peer_connection.on("icegatheringstatechange")
    def on_ice_gathering_state_change() -> None:
        if peer_connection.iceGatheringState == "complete":
            complete.set()

    await complete.wait()
