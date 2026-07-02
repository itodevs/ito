import asyncio

from server.ito.app import ItoServer, ConnectionState
from server.ito.config import ServerConfig
from server.ito.protocol import (
    ROLE_PILOT_CLIENT,
    ROLE_ROBOT_DRIVER,
    ROBOT_STATUS_AVAILABLE,
    ROBOT_STATUS_UNAVAILABLE,
    ROBOT_TYPE_DROID,
    TYPE_CATALOG_GET,
    TYPE_CATALOG_GET_RESULT,
    TYPE_CONNECTION_HELLO,
    TYPE_CONNECTION_HELLO_RESULT,
    TYPE_ROBOT_STATUS,
    make_envelope,
    pack_envelope,
    unpack_envelope,
)


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(unpack_envelope(frame))


def state():
    return ConnectionState(websocket=FakeWebSocket())


def test_pilot_hello_and_empty_catalog():
    asyncio.run(_pilot_hello_and_empty_catalog())


async def _pilot_hello_and_empty_catalog():
    server = ItoServer(ServerConfig(driver_status_watchdog_ms=1000))
    pilot = state()

    await server._handle_frame(
        pilot,
        pack_envelope(
            make_envelope(TYPE_CONNECTION_HELLO, {"role": ROLE_PILOT_CLIENT}, message_id="hello-1")
        ),
    )
    await server._handle_frame(
        pilot,
        pack_envelope(make_envelope(TYPE_CATALOG_GET, {"includeUnavailable": True}, message_id="cat-1")),
    )

    hello = pilot.websocket.sent[0]
    catalog = pilot.websocket.sent[1]
    assert hello["type"] == TYPE_CONNECTION_HELLO_RESULT
    assert hello["payload"]["ok"] is True
    assert catalog["type"] == TYPE_CATALOG_GET_RESULT
    assert catalog["replyToMessageId"] == "cat-1"
    assert catalog["payload"] == {"ok": True, "value": {"robots": []}}


def test_driver_status_populates_catalog():
    asyncio.run(_driver_status_populates_catalog())


async def _driver_status_populates_catalog():
    server = ItoServer(ServerConfig(driver_status_watchdog_ms=1000))
    driver = state()
    pilot = state()

    await server._handle_frame(
        driver,
        pack_envelope(
            make_envelope(
                TYPE_CONNECTION_HELLO,
                {"role": ROLE_ROBOT_DRIVER, "robotId": "droid-1"},
                message_id="driver-hello",
            )
        ),
    )
    await server._handle_frame(
        driver,
        pack_envelope(
            make_envelope(
                TYPE_ROBOT_STATUS,
                {"name": "Dory", "type": ROBOT_TYPE_DROID, "status": ROBOT_STATUS_AVAILABLE},
                robot_id="droid-1",
            )
        ),
    )
    await server._handle_frame(
        pilot,
        pack_envelope(make_envelope(TYPE_CONNECTION_HELLO, {"role": ROLE_PILOT_CLIENT})),
    )
    await server._handle_frame(pilot, pack_envelope(make_envelope(TYPE_CATALOG_GET)))

    robots = pilot.websocket.sent[-1]["payload"]["value"]["robots"]
    assert robots == [
        {
            "robotId": "droid-1",
            "name": "Dory",
            "type": ROBOT_TYPE_DROID,
            "status": ROBOT_STATUS_AVAILABLE,
        }
    ]


def test_duplicate_robot_id_is_cataloged_unavailable():
    asyncio.run(_duplicate_robot_id_is_cataloged_unavailable())


async def _duplicate_robot_id_is_cataloged_unavailable():
    server = ItoServer(ServerConfig(driver_status_watchdog_ms=1000))
    first = state()
    second = state()
    pilot = state()

    for conn in (first, second):
        await server._handle_frame(
            conn,
            pack_envelope(
                make_envelope(
                    TYPE_CONNECTION_HELLO,
                    {"role": ROLE_ROBOT_DRIVER, "robotId": "droid-1"},
                )
            ),
        )
    await server._handle_frame(pilot, pack_envelope(make_envelope(TYPE_CONNECTION_HELLO, {"role": ROLE_PILOT_CLIENT})))
    await server._handle_frame(pilot, pack_envelope(make_envelope(TYPE_CATALOG_GET)))

    robots = pilot.websocket.sent[-1]["payload"]["value"]["robots"]
    assert robots[0]["robotId"] == "droid-1"
    assert robots[0]["status"] == ROBOT_STATUS_UNAVAILABLE
