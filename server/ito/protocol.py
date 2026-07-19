"""Network messages for one Ito application, one pilot, and one robot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

import msgpack

PROTOCOL_VERSION = "ito.v1"

TYPE_CONNECTION_HELLO = "connection.hello"
TYPE_CONNECTION_HELLO_RESULT = "connection.hello.result"
TYPE_CONTROL_START = "control.start"
TYPE_CONTROL_START_RESULT = "control.start.result"
TYPE_CONTROL_STOP = "control.stop"
TYPE_CONTROL_STOP_RESULT = "control.stop.result"
TYPE_CONTROL_STOPPED = "control.stopped"
TYPE_ROBOT_READY = "robot.ready"
TYPE_DRIVER_CONTROL_START = "driver.control.start"
TYPE_DRIVER_CONTROL_START_RESULT = "driver.control.start.result"
TYPE_DRIVER_CONTROL_STOP = "driver.control.stop"
TYPE_DRIVER_CONTROL_STOP_RESULT = "driver.control.stop.result"
TYPE_WEBRTC_OFFER = "webrtc.offer"
TYPE_WEBRTC_ANSWER = "webrtc.answer"

WEBRTC_PATH_PILOT_INPUT = "pilotInput"
WEBRTC_PATH_CAMERA_MEDIA = "cameraMedia"
WEBRTC_PATH_SPLAT_BATCHES = "splatBatches"
WEBRTC_PATHS = frozenset(
    {WEBRTC_PATH_PILOT_INPUT, WEBRTC_PATH_CAMERA_MEDIA, WEBRTC_PATH_SPLAT_BATCHES}
)

MESSAGE_TYPES = frozenset(
    {
        TYPE_CONNECTION_HELLO,
        TYPE_CONNECTION_HELLO_RESULT,
        TYPE_CONTROL_START,
        TYPE_CONTROL_START_RESULT,
        TYPE_CONTROL_STOP,
        TYPE_CONTROL_STOP_RESULT,
        TYPE_CONTROL_STOPPED,
        TYPE_ROBOT_READY,
        TYPE_DRIVER_CONTROL_START,
        TYPE_DRIVER_CONTROL_START_RESULT,
        TYPE_DRIVER_CONTROL_STOP,
        TYPE_DRIVER_CONTROL_STOP_RESULT,
        TYPE_WEBRTC_OFFER,
        TYPE_WEBRTC_ANSWER,
    }
)

ROLE_PILOT_CLIENT = "pilotClient"
ROLE_REMOTE_ROBOT_DRIVER = "remoteRobotDriver"
ROLES = frozenset({ROLE_PILOT_CLIENT, ROLE_REMOTE_ROBOT_DRIVER})


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class DisplayReason:
    code: str | None = None
    text: str | None = None

    def __post_init__(self) -> None:
        if not self.code and not self.text:
            raise ValueError("display reason requires code or text")

    def to_payload(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        if self.code:
            payload["code"] = self.code
        if self.text:
            payload["text"] = self.text
        return payload


def make_envelope(
    message_type: str,
    payload: Mapping[str, Any] | None = None,
    *,
    message_id: str | None = None,
    reply_to_message_id: str | None = None,
) -> dict[str, Any]:
    if message_type not in MESSAGE_TYPES:
        raise ProtocolError(f"unsupported message type: {message_type}")
    envelope: dict[str, Any] = {
        "protocolVersion": PROTOCOL_VERSION,
        "messageId": message_id or str(uuid4()),
        "type": message_type,
        "payload": dict(payload or {}),
    }
    if reply_to_message_id is not None:
        envelope["replyToMessageId"] = reply_to_message_id
    return envelope


def pack_envelope(envelope: Mapping[str, Any]) -> bytes:
    validate_envelope(envelope)
    return msgpack.packb(dict(envelope), use_bin_type=True)


def unpack_envelope(frame: bytes) -> dict[str, Any]:
    try:
        envelope = msgpack.unpackb(frame, raw=False)
    except (ValueError, msgpack.ExtraData) as exc:
        raise ProtocolError("invalid MessagePack envelope") from exc
    validate_envelope(envelope)
    return dict(envelope)


def validate_envelope(envelope: Mapping[str, Any]) -> None:
    if not isinstance(envelope, Mapping):
        raise ProtocolError("envelope must be a map")
    validate_protocol_version(envelope.get("protocolVersion"))
    if not isinstance(envelope.get("messageId"), str) or not envelope["messageId"]:
        raise ProtocolError("messageId must be a non-empty string")
    if envelope.get("type") not in MESSAGE_TYPES:
        raise ProtocolError("unknown message type")
    if not isinstance(envelope.get("payload"), Mapping):
        raise ProtocolError("payload must be a map")
    reply_to = envelope.get("replyToMessageId")
    if reply_to is not None and not isinstance(reply_to, str):
        raise ProtocolError("replyToMessageId must be a string")
    if "robotId" in envelope or "sessionId" in envelope:
        raise ProtocolError("robot and session identifiers aren't part of this protocol")


def validate_protocol_version(version: object) -> None:
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"protocolVersion must be {PROTOCOL_VERSION}")


def result_ok(value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, "value": dict(value or {})}


def result_error(reason: DisplayReason) -> dict[str, Any]:
    return {"ok": False, "reason": reason.to_payload()}
