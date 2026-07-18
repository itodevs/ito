"""Driver-side WebRTC helpers for Ito Droid live paths."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Mapping

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
    if not isinstance(payload.get("headsetYawRad"), (int, float)):
        raise ValueError("snapshot requires headsetYawRad")
    if not isinstance(payload.get("controllers"), list):
        raise ValueError("snapshot requires controllers")
    return payload
