import pytest

from server.ito.protocol import (
    DisplayReason,
    PROTOCOL_VERSION,
    ProtocolError,
    TYPE_CONNECTION_HELLO,
    make_envelope,
    pack_envelope,
    result_error,
    result_ok,
    unpack_envelope,
    validate_protocol_version,
)


def test_pack_round_trip_envelope():
    envelope = make_envelope(
        TYPE_CONNECTION_HELLO,
        {"role": "pilotClient"},
        message_id="msg-1",
        session_id="session-1",
    )

    assert unpack_envelope(pack_envelope(envelope)) == envelope


def test_rejects_protocol_version_mismatch():
    with pytest.raises(ProtocolError):
        validate_protocol_version("ito.v0")


def test_result_helpers_build_standard_payloads():
    assert result_ok({"protocolVersion": PROTOCOL_VERSION}) == {
        "ok": True,
        "value": {"protocolVersion": PROTOCOL_VERSION},
    }
    assert result_error(DisplayReason(code="request.timeout")) == {
        "ok": False,
        "reason": {"code": "request.timeout"},
    }


def test_display_reason_requires_code_or_text():
    with pytest.raises(ValueError):
        DisplayReason()
