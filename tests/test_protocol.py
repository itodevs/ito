import pytest

from server.ito.protocol import (
    MESSAGE_TYPES,
    PROTOCOL_VERSION,
    TYPE_CONNECTION_HELLO,
    TYPE_CONTROL_START,
    TYPE_CONTROL_STOP,
    ProtocolError,
    make_envelope,
    pack_envelope,
    unpack_envelope,
)


def test_protocol_has_direct_control_without_catalog_or_allocation_messages():
    assert TYPE_CONTROL_START in MESSAGE_TYPES
    assert TYPE_CONTROL_STOP in MESSAGE_TYPES
    assert not any("catalog" in message_type for message_type in MESSAGE_TYPES)
    assert not any("acquire" in message_type for message_type in MESSAGE_TYPES)
    assert not any("reservation" in message_type for message_type in MESSAGE_TYPES)


def test_envelopes_have_no_robot_or_session_identity():
    envelope = make_envelope(
        TYPE_CONNECTION_HELLO,
        {"role": "pilotClient"},
        message_id="msg-1",
    )

    assert unpack_envelope(pack_envelope(envelope)) == {
        "protocolVersion": PROTOCOL_VERSION,
        "messageId": "msg-1",
        "type": TYPE_CONNECTION_HELLO,
        "payload": {"role": "pilotClient"},
    }


def test_unknown_message_type_is_rejected():
    with pytest.raises(ProtocolError):
        make_envelope("catalog.get", {})
