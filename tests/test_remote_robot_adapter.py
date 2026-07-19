import asyncio

from server.ito.protocol import (
    TYPE_DRIVER_CONTROL_START,
    TYPE_DRIVER_CONTROL_START_RESULT,
    TYPE_WEBRTC_ANSWER,
    TYPE_WEBRTC_OFFER,
    make_envelope,
    unpack_envelope,
)
from server.ito.robot import RemoteRobotAdapter


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(unpack_envelope(frame))


def test_remote_adapter_starts_the_one_attached_driver():
    async def scenario():
        websocket = FakeWebSocket()
        adapter = RemoteRobotAdapter(request_timeout_ms=1000)
        adapter.attach(websocket, ready=True)

        starting = asyncio.create_task(adapter.start_control())
        await asyncio.sleep(0)
        request = websocket.sent[-1]
        assert request["type"] == TYPE_DRIVER_CONTROL_START
        adapter.handle_response(
            make_envelope(
                TYPE_DRIVER_CONTROL_START_RESULT,
                {"ok": True, "value": {}},
                reply_to_message_id=request["messageId"],
            )
        )
        await starting

        assert adapter.control_active is True
        assert adapter.ready is True

    asyncio.run(scenario())


def test_remote_adapter_relays_pilot_input_negotiation_without_identity():
    async def scenario():
        websocket = FakeWebSocket()
        adapter = RemoteRobotAdapter(request_timeout_ms=1000)
        adapter.attach(websocket, ready=True)

        negotiating = asyncio.create_task(
            adapter.accept_pilot_input_offer("pilot offer")
        )
        await asyncio.sleep(0)
        offer = websocket.sent[-1]
        assert offer["type"] == TYPE_WEBRTC_OFFER
        assert offer["payload"] == {"path": "pilotInput", "sdp": "pilot offer"}
        assert "robotId" not in offer
        assert "sessionId" not in offer
        adapter.handle_response(
            make_envelope(
                TYPE_WEBRTC_ANSWER,
                {"path": "pilotInput", "sdp": "driver answer"},
                reply_to_message_id=offer["messageId"],
            )
        )

        assert await negotiating == "driver answer"

    asyncio.run(scenario())
