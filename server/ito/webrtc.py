"""Server-side WebRTC live-path seams."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any, Awaitable, Callable, Mapping, Protocol

from .protocol import (
    PROTOCOL_VERSION,
    WEBRTC_PATH_CAMERA_MEDIA,
    WEBRTC_PATH_PILOT_INPUT,
    WEBRTC_PATH_SPLAT_BATCHES,
)

LOGGER = logging.getLogger(__name__)


class ServerLivePathAcceptor(Protocol):
    async def accept_offer(self, *, path: str, control_key: str, sdp: str) -> str:
        ...


class MissingWebRtcStack:
    async def accept_offer(self, *, path: str, control_key: str, sdp: str) -> str:
        raise RuntimeError("aiortc is required for server-terminated WebRTC live paths")


class SplatBatchChannelRegistry:
    """Tracks the open Ito-to-client Splat Batch data channel."""

    def __init__(self) -> None:
        self.channels: dict[str, object] = {}

    def attach(self, control_key: str, data_channel: object) -> None:
        self.channels[control_key] = data_channel

    def detach(self, control_key: str, data_channel: object | None = None) -> None:
        if data_channel is None or self.channels.get(control_key) is data_channel:
            self.channels.pop(control_key, None)

    def send(self, control_key: str, payload: bytes) -> bool:
        channel = self.channels.get(control_key)
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
    on_pilot_input: Callable[[Mapping[str, Any]], None] | None = None
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

    async def accept_offer(self, *, path: str, control_key: str, sdp: str) -> str:
        if path not in {
            WEBRTC_PATH_CAMERA_MEDIA,
            WEBRTC_PATH_PILOT_INPUT,
            WEBRTC_PATH_SPLAT_BATCHES,
        }:
            raise ValueError(f"server cannot terminate WebRTC path {path}")
        pc = self._peer_connection_type(configuration=self._configuration_type(iceServers=[]))
        self.peer_connections[(control_key, path)] = pc

        if path == WEBRTC_PATH_CAMERA_MEDIA and self.on_camera_track is not None:
            @pc.on("track")
            async def on_track(track: object) -> None:
                result = self.on_camera_track(track, control_key)
                if result is not None:
                    await result

        if path == WEBRTC_PATH_PILOT_INPUT and self.on_pilot_input is not None:
            @pc.on("datachannel")
            def on_data_channel(channel: object) -> None:
                @channel.on("message")
                def on_message(message: str | bytes) -> None:
                    try:
                        self.on_pilot_input(decode_pilot_input_snapshot(message))
                    except ValueError as exc:
                        LOGGER.warning("Ignoring invalid pilot input: %s", exc)

        if path == WEBRTC_PATH_SPLAT_BATCHES:
            channel = pc.createDataChannel("ito.splatBatches", ordered=True)
            if self.splat_channels is not None:
                @channel.on("open")
                def on_open() -> None:
                    self.splat_channels.attach(control_key, channel)

                @channel.on("close")
                def on_close() -> None:
                    self.splat_channels.detach(control_key, channel)
            if self.on_splat_channel is not None:
                result = self.on_splat_channel(channel, control_key)
                if result is not None:
                    await result

        offer = self._session_description_type(sdp=sdp, type="offer")
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await _wait_for_ice_gathering_complete(pc)
        return pc.localDescription.sdp

    async def close_control(self, control_key: str) -> None:
        import asyncio

        peers = [
            self.peer_connections.pop(key)
            for key in list(self.peer_connections)
            if key[0] == control_key
        ]
        if self.splat_channels is not None:
            self.splat_channels.detach(control_key)
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


def decode_pilot_input_snapshot(message: str | bytes) -> dict[str, Any]:
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    try:
        payload = json.loads(message)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("pilot input isn't valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("pilot input must be an object")
    if payload.get("protocolVersion") != PROTOCOL_VERSION:
        raise ValueError(f"pilot input protocolVersion must be {PROTOCOL_VERSION}")
    if not isinstance(payload.get("sequence"), int):
        raise ValueError("pilot input requires an integer sequence")
    if not isinstance(payload.get("timestampMs"), (int, float)):
        raise ValueError("pilot input requires timestampMs")
    if not isinstance(payload.get("headsetYawRad"), (int, float)):
        raise ValueError("pilot input requires headsetYawRad")
    if not isinstance(payload.get("controllers"), list):
        raise ValueError("pilot input requires a controllers list")
    return payload
