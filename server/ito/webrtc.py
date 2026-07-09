"""Server-side WebRTC live-path seams."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from .protocol import WEBRTC_PATH_CAMERA_MEDIA, WEBRTC_PATH_SPLAT_BATCHES


class ServerLivePathAcceptor(Protocol):
    async def accept_offer(self, *, path: str, session_id: str, sdp: str) -> str:
        ...


class MissingWebRtcStack:
    async def accept_offer(self, *, path: str, session_id: str, sdp: str) -> str:
        raise RuntimeError("aiortc is required for server-terminated WebRTC live paths")


class SplatBatchChannelRegistry:
    """Tracks open server-to-client Splat Batch data channels by session."""

    def __init__(self) -> None:
        self.channels: dict[str, object] = {}

    def attach(self, session_id: str, data_channel: object) -> None:
        self.channels[session_id] = data_channel

    def detach(self, session_id: str, data_channel: object | None = None) -> None:
        if data_channel is None or self.channels.get(session_id) is data_channel:
            self.channels.pop(session_id, None)

    def send(self, session_id: str, payload: bytes) -> bool:
        channel = self.channels.get(session_id)
        if channel is None or getattr(channel, "readyState", None) != "open":
            return False
        channel.send(payload)
        return True


@dataclass
class AiortcServerLivePaths:
    """Minimal aiortc-backed acceptor for server-terminated WebRTC paths.

    Camera media and Splat Batch transport are owned by the server. Production
    reconstruction integration attaches track/data-channel handlers here.
    """

    on_camera_track: Callable[[object, str], Awaitable[None] | None] | None = None
    on_splat_channel: Callable[[object, str], Awaitable[None] | None] | None = None
    splat_channels: SplatBatchChannelRegistry | None = None

    def __post_init__(self) -> None:
        try:
            from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("aiortc is required for WebRTC live paths") from exc
        self._configuration_type = RTCConfiguration
        self._peer_connection_type = RTCPeerConnection
        self._session_description_type = RTCSessionDescription
        self.peer_connections: dict[tuple[str, str], object] = {}

    async def accept_offer(self, *, path: str, session_id: str, sdp: str) -> str:
        if path not in {WEBRTC_PATH_CAMERA_MEDIA, WEBRTC_PATH_SPLAT_BATCHES}:
            raise ValueError(f"server cannot terminate WebRTC path {path}")
        pc = self._peer_connection_type(configuration=self._configuration_type(iceServers=[]))
        self.peer_connections[(session_id, path)] = pc

        if path == WEBRTC_PATH_CAMERA_MEDIA and self.on_camera_track is not None:
            @pc.on("track")
            async def on_track(track: object) -> None:
                result = self.on_camera_track(track, session_id)
                if result is not None:
                    await result

        if path == WEBRTC_PATH_SPLAT_BATCHES:
            channel = pc.createDataChannel("ito.splatBatches", ordered=True)
            if self.splat_channels is not None:
                @channel.on("open")
                def on_open() -> None:
                    self.splat_channels.attach(session_id, channel)

                @channel.on("close")
                def on_close() -> None:
                    self.splat_channels.detach(session_id, channel)
            if self.on_splat_channel is not None:
                result = self.on_splat_channel(channel, session_id)
                if result is not None:
                    await result

        offer = self._session_description_type(sdp=sdp, type="offer")
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await _wait_for_ice_gathering_complete(pc)
        return pc.localDescription.sdp

    async def close_session(self, session_id: str) -> None:
        import asyncio

        peers = [
            self.peer_connections.pop(key)
            for key in list(self.peer_connections)
            if key[0] == session_id
        ]
        if self.splat_channels is not None:
            self.splat_channels.detach(session_id)
        await asyncio.gather(*(pc.close() for pc in peers), return_exceptions=True)


async def _wait_for_ice_gathering_complete(peer_connection: object) -> None:
    if getattr(peer_connection, "iceGatheringState", None) == "complete":
        return
    import asyncio

    complete = asyncio.Event()

    @peer_connection.on("icegatheringstatechange")
    def on_ice_gathering_state_change() -> None:
        if peer_connection.iceGatheringState == "complete":
            complete.set()

    await complete.wait()
