"""Mock Robot WebRTC live-path helpers."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Mapping

LOGGER = logging.getLogger(__name__)


class PilotInputWebRtcReceiver:
    """Accepts pilot-input WebRTC offers and forwards snapshots to a sink."""

    def __init__(self, receive_snapshot: Callable[[Mapping[str, Any]], None]) -> None:
        try:
            from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        except ImportError as exc:  # pragma: no cover - declared runtime dependency
            raise RuntimeError("aiortc is required for Mock Robot WebRTC pilot input") from exc
        self._configuration_type = RTCConfiguration
        self._peer_connection_type = RTCPeerConnection
        self._session_description_type = RTCSessionDescription
        self._receive_snapshot = receive_snapshot
        self._peer_connections: dict[str, Any] = {}

    async def accept_offer(self, *, control_key: str, sdp: str) -> str:
        pc = self._peer_connection_type(configuration=self._configuration_type(iceServers=[]))
        self._peer_connections[control_key] = pc

        @pc.on("datachannel")
        def on_data_channel(channel: Any) -> None:
            @channel.on("message")
            def on_message(message: str | bytes) -> None:
                try:
                    self._receive_snapshot(decode_pilot_input_snapshot(message))
                except ValueError as exc:
                    LOGGER.warning("Ignoring invalid Pilot Input Snapshot: %s", exc)

        offer = self._session_description_type(sdp=sdp, type="offer")
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await _wait_for_ice_gathering_complete(pc)
        return pc.localDescription.sdp

    async def close_control(self, control_key: str) -> None:
        pc = self._peer_connections.pop(control_key, None)
        if pc is not None:
            await pc.close()

    async def close_all(self) -> None:
        peer_connections = list(self._peer_connections.values())
        self._peer_connections.clear()
        await asyncio.gather(*(pc.close() for pc in peer_connections), return_exceptions=True)


class CameraMediaWebRtcPublisher:
    """Publishes a video file to the server over the `cameraMedia` WebRTC path."""

    def __init__(self) -> None:
        try:
            from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
            from aiortc.contrib.media import MediaPlayer
        except ImportError as exc:  # pragma: no cover - declared runtime dependency
            raise RuntimeError("aiortc is required for Mock Robot camera media") from exc
        self._configuration_type = RTCConfiguration
        self._peer_connection_type = RTCPeerConnection
        self._session_description_type = RTCSessionDescription
        self._media_player_type = MediaPlayer
        self._peer_connections: dict[str, Any] = {}
        self._players: dict[str, Any] = {}

    async def create_offer(self, *, control_key: str, video_path: str | Path, loop: bool) -> str:
        pc = self._peer_connection_type(configuration=self._configuration_type(iceServers=[]))
        player = self._media_player_type(str(video_path), loop=loop)
        if player.video is None:
            await pc.close()
            raise RuntimeError(f"mock camera video has no video stream: {video_path}")
        pc.addTrack(player.video)
        self._prefer_h264(pc)
        self._peer_connections[control_key] = pc
        self._players[control_key] = player
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await _wait_for_ice_gathering_complete(pc)
        return pc.localDescription.sdp

    async def accept_answer(self, *, control_key: str, sdp: str) -> None:
        pc = self._peer_connections.get(control_key)
        if pc is None:
            raise RuntimeError("no cameraMedia peer connection for active control")
        await pc.setRemoteDescription(self._session_description_type(sdp=sdp, type="answer"))

    async def close_control(self, control_key: str) -> None:
        pc = self._peer_connections.pop(control_key, None)
        player = self._players.pop(control_key, None)
        if player is not None and player.video is not None:
            player.video.stop()
        if pc is not None:
            await pc.close()

    async def close_all(self) -> None:
        peer_connections = list(self._peer_connections.values())
        players = list(self._players.values())
        self._peer_connections.clear()
        self._players.clear()
        for player in players:
            if player.video is not None:
                player.video.stop()
        await asyncio.gather(*(pc.close() for pc in peer_connections), return_exceptions=True)

    def _prefer_h264(self, pc: Any) -> None:
        try:
            from aiortc import RTCRtpSender
        except ImportError:  # pragma: no cover - already imported in __init__
            return
        codecs = [
            codec
            for codec in RTCRtpSender.getCapabilities("video").codecs
            if codec.mimeType.lower() == "video/h264"
        ]
        if not codecs:
            return
        for transceiver in pc.getTransceivers():
            if transceiver.kind == "video":
                transceiver.setCodecPreferences(codecs)


def decode_pilot_input_snapshot(message: str | bytes) -> dict[str, Any]:
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    try:
        payload = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError("snapshot is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("snapshot must be a JSON object")
    if payload.get("protocolVersion") != "ito.v1":
        raise ValueError("snapshot protocolVersion must be ito.v1")
    if not isinstance(payload.get("sequence"), int):
        raise ValueError("snapshot requires integer sequence")
    if not isinstance(payload.get("timestampMs"), (int, float)):
        raise ValueError("snapshot requires timestampMs")
    if not isinstance(payload.get("headsetYawRad"), (int, float)):
        raise ValueError("snapshot requires headsetYawRad")
    if not isinstance(payload.get("controllers"), list):
        raise ValueError("snapshot requires controllers")
    return payload


async def _wait_for_ice_gathering_complete(peer_connection: Any) -> None:
    if getattr(peer_connection, "iceGatheringState", None) == "complete":
        return

    complete = asyncio.Event()

    @peer_connection.on("icegatheringstatechange")
    def on_ice_gathering_state_change() -> None:
        if peer_connection.iceGatheringState == "complete":
            complete.set()

    await complete.wait()
