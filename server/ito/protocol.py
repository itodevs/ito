"""Shared Ito v1 protocol constants and MessagePack envelope helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

import msgpack

PROTOCOL_VERSION = "ito.v1"

TYPE_CATALOG_GET = "catalog.get"
TYPE_CATALOG_GET_RESULT = "catalog.get.result"
TYPE_CONNECTION_HELLO = "connection.hello"
TYPE_CONNECTION_HELLO_RESULT = "connection.hello.result"
TYPE_ROBOT_STATUS = "robot.status"
TYPE_SESSION_ACQUIRE = "session.acquire"
TYPE_SESSION_ACQUIRE_RESULT = "session.acquire.result"
TYPE_DRIVER_SESSION_START = "driver.session.start"
TYPE_DRIVER_SESSION_START_RESULT = "driver.session.start.result"
TYPE_SESSION_END = "session.end"
TYPE_SESSION_END_RESULT = "session.end.result"
TYPE_SESSION_ENDED = "session.ended"
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
        TYPE_CATALOG_GET,
        TYPE_CATALOG_GET_RESULT,
        TYPE_CONNECTION_HELLO,
        TYPE_CONNECTION_HELLO_RESULT,
        TYPE_ROBOT_STATUS,
        TYPE_SESSION_ACQUIRE,
        TYPE_SESSION_ACQUIRE_RESULT,
        TYPE_DRIVER_SESSION_START,
        TYPE_DRIVER_SESSION_START_RESULT,
        TYPE_SESSION_END,
        TYPE_SESSION_END_RESULT,
        TYPE_SESSION_ENDED,
        TYPE_WEBRTC_OFFER,
        TYPE_WEBRTC_ANSWER,
    }
)

ROLE_PILOT_CLIENT = "pilotClient"
ROLE_ROBOT_DRIVER = "robotDriver"
ROLES = frozenset({ROLE_PILOT_CLIENT, ROLE_ROBOT_DRIVER})

ROBOT_STATUS_AVAILABLE = "Available"
ROBOT_STATUS_OCCUPIED = "Occupied"
ROBOT_STATUS_UNAVAILABLE = "Unavailable"
ROBOT_STATUSES = frozenset(
    {ROBOT_STATUS_AVAILABLE, ROBOT_STATUS_OCCUPIED, ROBOT_STATUS_UNAVAILABLE}
)

ROBOT_TYPE_MECHA = "Mecha"
ROBOT_TYPE_ANDROID_ROBOT = "Android Robot"
ROBOT_TYPE_DROID = "Droid"
ROBOT_TYPE_DRONE = "Drone"
ROBOT_TYPE_CAR = "Car"
ROBOT_TYPE_PLANE = "Plane"
ROBOT_TYPES = frozenset(
    {
        ROBOT_TYPE_MECHA,
        ROBOT_TYPE_ANDROID_ROBOT,
        ROBOT_TYPE_DROID,
        ROBOT_TYPE_DRONE,
        ROBOT_TYPE_CAR,
        ROBOT_TYPE_PLANE,
    }
)

REASON_PROTOCOL_VERSION_MISMATCH = "protocol.version_mismatch"
REASON_INVALID_MESSAGE = "protocol.invalid_message"
REASON_REQUEST_TIMEOUT = "request.timeout"


class ProtocolError(ValueError):
    """Raised when a decoded control-plane message violates Ito Protocol."""


@dataclass(frozen=True)
class DisplayReason:
    """Pilot-displayable reason represented by resource key and/or free text."""

    code: str | None = None
    text: str | None = None

    def __post_init__(self) -> None:
        if not self.code and not self.text:
            raise ValueError("DisplayReason requires code, text, or both")

    def to_payload(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        if self.code:
            payload["code"] = self.code
        if self.text:
            payload["text"] = self.text
        return payload


def result_ok(value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the standard successful request/result payload."""

    return {"ok": True, "value": dict(value or {})}


def result_error(reason: DisplayReason | Mapping[str, str]) -> dict[str, Any]:
    """Build the standard failed request/result payload."""

    reason_payload = reason.to_payload() if isinstance(reason, DisplayReason) else dict(reason)
    validate_display_reason(reason_payload)
    return {"ok": False, "reason": reason_payload}


def make_message_id() -> str:
    """Generate a sender-owned unique message identifier."""

    return str(uuid4())


def make_envelope(
    message_type: str,
    payload: Mapping[str, Any] | None = None,
    *,
    message_id: str | None = None,
    reply_to_message_id: str | None = None,
    robot_id: str | None = None,
    session_id: str | None = None,
    protocol_version: str = PROTOCOL_VERSION,
) -> dict[str, Any]:
    """Create a decoded Ito control-plane envelope."""

    if message_type not in MESSAGE_TYPES:
        raise ProtocolError(f"unknown Ito message type: {message_type}")

    envelope: dict[str, Any] = {
        "protocolVersion": protocol_version,
        "messageId": message_id or make_message_id(),
        "type": message_type,
        "payload": dict(payload or {}),
    }
    if reply_to_message_id is not None:
        envelope["replyToMessageId"] = reply_to_message_id
    if robot_id is not None:
        envelope["robotId"] = robot_id
    if session_id is not None:
        envelope["sessionId"] = session_id
    validate_envelope(envelope)
    return envelope


def validate_protocol_version(protocol_version: str) -> None:
    if protocol_version != PROTOCOL_VERSION:
        raise ProtocolError(
            f"unsupported Ito protocol version {protocol_version!r}; expected {PROTOCOL_VERSION!r}"
        )


def validate_display_reason(reason: Mapping[str, Any]) -> None:
    code = reason.get("code")
    text = reason.get("text")
    if not isinstance(reason, Mapping) or (not code and not text):
        raise ProtocolError("Display Reason requires code, text, or both")
    if code is not None and not isinstance(code, str):
        raise ProtocolError("Display Reason code must be a string")
    if text is not None and not isinstance(text, str):
        raise ProtocolError("Display Reason text must be a string")


def validate_envelope(envelope: Mapping[str, Any]) -> None:
    if not isinstance(envelope, Mapping):
        raise ProtocolError("Ito envelope must be a map")
    validate_protocol_version(envelope.get("protocolVersion"))
    if not isinstance(envelope.get("messageId"), str) or not envelope["messageId"]:
        raise ProtocolError("Ito envelope requires non-empty string messageId")
    if envelope.get("replyToMessageId") is not None and not isinstance(
        envelope.get("replyToMessageId"), str
    ):
        raise ProtocolError("replyToMessageId must be a string when present")
    if envelope.get("type") not in MESSAGE_TYPES:
        raise ProtocolError(f"unknown Ito message type: {envelope.get('type')!r}")
    if "payload" not in envelope or not isinstance(envelope.get("payload"), Mapping):
        raise ProtocolError("Ito envelope requires payload map")
    for field in ("robotId", "sessionId"):
        if envelope.get(field) is not None and not isinstance(envelope.get(field), str):
            raise ProtocolError(f"{field} must be a string when present")
    if envelope.get("type") in {TYPE_WEBRTC_OFFER, TYPE_WEBRTC_ANSWER}:
        validate_webrtc_signal_payload(envelope["payload"])


def validate_webrtc_signal_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("path") not in WEBRTC_PATHS:
        raise ProtocolError(f"unknown WebRTC live path: {payload.get('path')!r}")
    if not isinstance(payload.get("sdp"), str) or not payload["sdp"]:
        raise ProtocolError("WebRTC signaling payload requires non-empty SDP")


def pack_envelope(envelope: Mapping[str, Any]) -> bytes:
    """Validate and encode an envelope as a MessagePack binary WebSocket frame."""

    validate_envelope(envelope)
    return msgpack.packb(dict(envelope), use_bin_type=True)


def unpack_envelope(frame: bytes) -> dict[str, Any]:
    """Decode and validate a MessagePack binary WebSocket frame."""

    try:
        envelope = msgpack.unpackb(frame, raw=False, strict_map_key=False)
    except (msgpack.ExtraData, msgpack.FormatError, msgpack.StackError, ValueError) as exc:
        raise ProtocolError("invalid MessagePack Ito envelope") from exc
    validate_envelope(envelope)
    return dict(envelope)
