"""Mock Robot WebRTC live-path helpers."""

from __future__ import annotations

import asyncio
import json
import logging
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

    async def accept_offer(self, *, session_id: str, sdp: str) -> str:
        pc = self._peer_connection_type(configuration=self._configuration_type(iceServers=[]))
        self._peer_connections[session_id] = pc

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

    async def close_session(self, session_id: str | None) -> None:
        if session_id is None:
            return
        pc = self._peer_connections.pop(session_id, None)
        if pc is not None:
            await pc.close()

    async def close_all(self) -> None:
        peer_connections = list(self._peer_connections.values())
        self._peer_connections.clear()
        await asyncio.gather(*(pc.close() for pc in peer_connections), return_exceptions=True)


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
    if not isinstance(payload.get("sessionId"), str):
        raise ValueError("snapshot requires sessionId")
    if not isinstance(payload.get("sequence"), int):
        raise ValueError("snapshot requires integer sequence")
    if not isinstance(payload.get("timestampMs"), (int, float)):
        raise ValueError("snapshot requires timestampMs")
    if not isinstance(payload.get("headsetYawRad"), (int, float)):
        raise ValueError("snapshot requires headsetYawRad")
    if not isinstance(payload.get("controllers"), dict):
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
