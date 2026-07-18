import asyncio
from pathlib import Path
from types import SimpleNamespace

from server.ito.app import ConnectionState, ItoApplication
from server.ito.config import ItoConfig
from server.ito.protocol import (
    ROLE_PILOT_CLIENT,
    ROLE_REMOTE_ROBOT_DRIVER,
    TYPE_CONNECTION_HELLO,
    TYPE_CONTROL_START,
    TYPE_CONTROL_START_RESULT,
    TYPE_CONTROL_STOP,
    TYPE_CONTROL_STOPPED,
    TYPE_ROBOT_READY,
    make_envelope,
    pack_envelope,
    unpack_envelope,
)
from server.ito.robot import LocalRobotAdapter
from server.ito.robot import RemoteRobotAdapter


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(unpack_envelope(frame))


def state():
    return ConnectionState(FakeWebSocket())


async def send(application, connection, message_type, payload, message_id):
    await application._handle_frame(
        connection,
        pack_envelope(make_envelope(message_type, payload, message_id=message_id)),
    )
    return connection.websocket.sent[-1]


async def hello(application, connection):
    return await send(
        application,
        connection,
        TYPE_CONNECTION_HELLO,
        {"role": ROLE_PILOT_CLIENT},
        "hello-1",
    )


def test_pilot_connects_directly_to_the_one_configured_robot():
    async def scenario():
        application = ItoApplication(adapter=LocalRobotAdapter())
        pilot = state()

        response = await hello(application, pilot)

        assert response["payload"] == {
            "ok": True,
            "value": {
                "protocolVersion": "ito.v1",
                "backend": "local",
                "robotReady": True,
                "controlActive": False,
                "controlConfig": application.config.control_config_payload(),
            },
        }
        assert "robotId" not in response
        assert "sessionId" not in response

    asyncio.run(scenario())


def test_start_and_stop_control_call_the_local_adapter_without_allocation():
    async def scenario():
        safe_stops = []
        adapter = LocalRobotAdapter(safe_stop=lambda: safe_stops.append(True))
        application = ItoApplication(adapter=adapter)
        pilot = state()
        await hello(application, pilot)

        started = await send(application, pilot, TYPE_CONTROL_START, {}, "start-1")
        stopped = await send(
            application,
            pilot,
            TYPE_CONTROL_STOP,
            {"reason": {"code": "control.stopped.pilot_requested"}},
            "stop-1",
        )

        assert started["type"] == TYPE_CONTROL_START_RESULT
        assert started["payload"]["ok"] is True
        assert stopped["type"] == TYPE_CONTROL_STOPPED
        assert application.control_active is False
        assert adapter.control_active is False
        assert safe_stops == [True]

    asyncio.run(scenario())


def test_second_simultaneous_pilot_is_rejected():
    async def scenario():
        application = ItoApplication(adapter=LocalRobotAdapter())
        first = state()
        second = state()
        await hello(application, first)

        response = await hello(application, second)

        assert response["payload"] == {
            "ok": False,
            "reason": {"code": "connection.pilot_already_connected"},
        }

    asyncio.run(scenario())


def test_pilot_disconnect_stops_control_locally():
    async def scenario():
        safe_stops = []
        adapter = LocalRobotAdapter(safe_stop=lambda: safe_stops.append(True))
        application = ItoApplication(adapter=adapter)
        pilot = state()
        await hello(application, pilot)
        await send(application, pilot, TYPE_CONTROL_START, {}, "start-1")

        await application._disconnect(pilot)

        assert application.control_active is False
        assert safe_stops == [True]

    asyncio.run(scenario())


def test_application_serves_the_webxr_client(tmp_path):
    client_dir = tmp_path / "client"
    client_dir.mkdir()
    (client_dir / "index.html").write_text("<h1>Ito Pilot</h1>")
    application = ItoApplication(
        config=ItoConfig(client_dir=client_dir),
        adapter=LocalRobotAdapter(),
    )

    response = asyncio.run(
        application.process_http_request(None, SimpleNamespace(path="/"))
    )

    assert response.status_code == 200
    assert response.body == b"<h1>Ito Pilot</h1>"
    assert response.headers["Content-Type"].startswith("text/html")


def test_remote_driver_is_configuration_not_a_client_visible_product_choice():
    async def scenario():
        adapter = RemoteRobotAdapter(request_timeout_ms=1000)
        application = ItoApplication(
            config=ItoConfig(robot_backend="remote"), adapter=adapter
        )
        driver = state()
        pilot = state()

        driver_response = await send(
            application,
            driver,
            TYPE_CONNECTION_HELLO,
            {"role": ROLE_REMOTE_ROBOT_DRIVER, "ready": True},
            "driver-hello",
        )
        pilot_response = await hello(application, pilot)

        assert driver_response["payload"]["ok"] is True
        assert pilot_response["payload"]["value"]["backend"] == "remote"
        assert pilot_response["payload"]["value"]["robotReady"] is True
        assert "robotId" not in pilot_response

    asyncio.run(scenario())


def test_pilot_is_notified_when_the_remote_driver_becomes_ready():
    async def scenario():
        adapter = RemoteRobotAdapter(request_timeout_ms=1000)
        application = ItoApplication(
            config=ItoConfig(robot_backend="remote"), adapter=adapter
        )
        pilot = state()
        driver = state()
        await hello(application, pilot)

        await send(
            application,
            driver,
            TYPE_CONNECTION_HELLO,
            {"role": ROLE_REMOTE_ROBOT_DRIVER, "ready": True},
            "driver-hello",
        )

        ready_event = pilot.websocket.sent[-1]
        assert ready_event["type"] == TYPE_ROBOT_READY
        assert ready_event["payload"] == {"ready": True}

    asyncio.run(scenario())


def test_remote_start_failure_returns_an_error_and_closes_reconstruction():
    class FailingAdapter(LocalRobotAdapter):
        async def start_control(self):
            raise RuntimeError("robot refused control")

    async def scenario():
        application = ItoApplication(adapter=FailingAdapter())
        pilot = state()
        await hello(application, pilot)

        response = await send(application, pilot, TYPE_CONTROL_START, {}, "start")

        assert response["type"] == TYPE_CONTROL_START_RESULT
        assert response["payload"] == {
            "ok": False,
            "reason": {"code": "control.start_failed", "text": "robot refused control"},
        }
        assert application.control_active is False
        assert application.reconstruction_runtime is None

    asyncio.run(scenario())
