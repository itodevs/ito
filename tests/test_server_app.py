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
    TYPE_DRIVER_SESSION_START,
    TYPE_DRIVER_SESSION_START_RESULT,
    TYPE_ROBOT_STATUS,
    TYPE_SESSION_ACQUIRE,
    TYPE_SESSION_ACQUIRE_RESULT,
    TYPE_SESSION_END,
    TYPE_SESSION_END_RESULT,
    TYPE_SESSION_ENDED,
    make_envelope,
    pack_envelope,
    result_error,
    result_ok,
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


async def hello_pilot(server, pilot, session_id=None):
    payload = {"role": ROLE_PILOT_CLIENT}
    if session_id:
        payload["sessionId"] = session_id
    await server._handle_frame(pilot, pack_envelope(make_envelope(TYPE_CONNECTION_HELLO, payload)))


async def hello_available_driver(server, driver, robot_id="droid-1"):
    await server._handle_frame(
        driver,
        pack_envelope(
            make_envelope(
                TYPE_CONNECTION_HELLO,
                {"role": ROLE_ROBOT_DRIVER, "robotId": robot_id},
                robot_id=robot_id,
            )
        ),
    )
    await server._handle_frame(
        driver,
        pack_envelope(
            make_envelope(
                TYPE_ROBOT_STATUS,
                {"name": "Dory", "type": ROBOT_TYPE_DROID, "status": ROBOT_STATUS_AVAILABLE},
                robot_id=robot_id,
            )
        ),
    )


async def acquire_task(server, pilot, robot_id="droid-1", message_id="acquire-1"):
    return asyncio.create_task(
        server._handle_frame(
            pilot,
            pack_envelope(
                make_envelope(
                    TYPE_SESSION_ACQUIRE,
                    {"robotId": robot_id},
                    message_id=message_id,
                    robot_id=robot_id,
                )
            ),
        )
    )


async def answer_driver_start(server, driver, ok=True):
    start = driver.websocket.sent[-1]
    assert start["type"] == TYPE_DRIVER_SESSION_START
    session_id = start["sessionId"]
    payload = result_ok({"sessionId": session_id}) if ok else result_error({"code": "driver.start_failed"})
    await server._handle_frame(
        driver,
        pack_envelope(
            make_envelope(
                TYPE_DRIVER_SESSION_START_RESULT,
                payload,
                reply_to_message_id=start["messageId"],
                robot_id="droid-1",
                session_id=session_id,
            )
        ),
    )
    return session_id


def test_acquire_reserves_robot_starts_driver_and_allocates_session():
    asyncio.run(_acquire_reserves_robot_starts_driver_and_allocates_session())


async def _acquire_reserves_robot_starts_driver_and_allocates_session():
    server = ItoServer(ServerConfig(request_timeout_ms=1000, driver_status_watchdog_ms=1000))
    driver = state()
    pilot = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, pilot)

    task = await acquire_task(server, pilot)
    await asyncio.sleep(0)

    assert server.drivers["droid-1"].occupied is True
    session_id = await answer_driver_start(server, driver)
    await task

    acquire = pilot.websocket.sent[-1]
    assert acquire["type"] == TYPE_SESSION_ACQUIRE_RESULT
    assert acquire["replyToMessageId"] == "acquire-1"
    assert acquire["payload"]["ok"] is True
    assert acquire["payload"]["value"]["sessionId"] == session_id
    assert acquire["payload"]["value"]["robotId"] == "droid-1"
    assert acquire["payload"]["value"]["sessionConfig"] == server.config.session_config_payload()
    assert server.sessions[session_id].state == "active"
    assert server.drivers["droid-1"].occupied is True


def test_acquisition_reservation_blocks_competing_pilot():
    asyncio.run(_acquisition_reservation_blocks_competing_pilot())


async def _acquisition_reservation_blocks_competing_pilot():
    server = ItoServer(ServerConfig(request_timeout_ms=1000, driver_status_watchdog_ms=1000))
    driver = state()
    first = state()
    second = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, first)
    await hello_pilot(server, second)

    first_task = await acquire_task(server, first, message_id="acquire-1")
    await asyncio.sleep(0)
    second_task = await acquire_task(server, second, message_id="acquire-2")
    await asyncio.sleep(0)

    assert len([msg for msg in driver.websocket.sent if msg["type"] == TYPE_DRIVER_SESSION_START]) == 1
    await answer_driver_start(server, driver)
    await first_task
    await second_task

    assert first.websocket.sent[-1]["payload"]["ok"] is True
    assert second.websocket.sent[-1]["type"] == TYPE_SESSION_ACQUIRE_RESULT
    assert second.websocket.sent[-1]["payload"] == {
        "ok": False,
        "reason": {"code": "session.acquire.robot_unavailable"},
    }


def test_driver_start_failure_releases_reservation():
    asyncio.run(_driver_start_failure_releases_reservation())


async def _driver_start_failure_releases_reservation():
    server = ItoServer(ServerConfig(request_timeout_ms=1000, driver_status_watchdog_ms=1000))
    driver = state()
    pilot = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, pilot)

    task = await acquire_task(server, pilot)
    await asyncio.sleep(0)
    session_id = await answer_driver_start(server, driver, ok=False)
    await task

    assert session_id not in server.sessions
    assert server.drivers["droid-1"].occupied is False
    assert pilot.websocket.sent[-1]["payload"] == {
        "ok": False,
        "reason": {"code": "driver.start_failed"},
    }


def test_driver_start_timeout_releases_reservation():
    asyncio.run(_driver_start_timeout_releases_reservation())


async def _driver_start_timeout_releases_reservation():
    server = ItoServer(ServerConfig(request_timeout_ms=1, driver_status_watchdog_ms=1000))
    driver = state()
    pilot = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, pilot)

    task = await acquire_task(server, pilot)
    await task

    assert server.sessions == {}
    assert server.drivers["droid-1"].occupied is False
    assert pilot.websocket.sent[-1]["type"] == TYPE_SESSION_ACQUIRE_RESULT
    assert pilot.websocket.sent[-1]["payload"] == {
        "ok": False,
        "reason": {"code": "request.timeout"},
    }


def test_session_end_marks_ended_and_fans_out():
    asyncio.run(_session_end_marks_ended_and_fans_out())


async def _session_end_marks_ended_and_fans_out():
    server = ItoServer(ServerConfig(request_timeout_ms=1000, driver_status_watchdog_ms=1000))
    driver = state()
    pilot = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, pilot)
    task = await acquire_task(server, pilot)
    await asyncio.sleep(0)
    session_id = await answer_driver_start(server, driver)
    await task

    await server._handle_frame(
        pilot,
        pack_envelope(
            make_envelope(
                TYPE_SESSION_END,
                {"reason": {"code": "session.ended.pilot_requested"}, "clean": True},
                message_id="end-1",
                session_id=session_id,
            )
        ),
    )

    assert pilot.websocket.sent[-2]["type"] == TYPE_SESSION_END_RESULT
    assert pilot.websocket.sent[-2]["payload"] == {"ok": True, "value": {"sessionId": session_id}}
    assert driver.websocket.sent[-2]["type"] == TYPE_SESSION_END
    assert pilot.websocket.sent[-1]["type"] == TYPE_SESSION_ENDED
    assert driver.websocket.sent[-1]["type"] == TYPE_SESSION_ENDED
    assert pilot.websocket.sent[-1]["payload"] == {
        "reason": {"code": "session.ended.pilot_requested"},
        "endedBy": ROLE_PILOT_CLIENT,
        "clean": True,
    }
    driver_sent_count = len(driver.websocket.sent)
    await server._handle_frame(
        driver,
        pack_envelope(
            make_envelope(
                TYPE_SESSION_END_RESULT,
                result_ok({"sessionId": session_id}),
                reply_to_message_id=driver.websocket.sent[-2]["messageId"],
                session_id=session_id,
            )
        ),
    )
    assert len(driver.websocket.sent) == driver_sent_count
    assert server.sessions[session_id].state == "ended"
    assert server.drivers["droid-1"].occupied is False


def test_cleanup_ends_session_after_disappeared_endpoint_timeout():
    asyncio.run(_cleanup_ends_session_after_disappeared_endpoint_timeout())


async def _cleanup_ends_session_after_disappeared_endpoint_timeout():
    server = ItoServer(
        ServerConfig(
            request_timeout_ms=1000,
            driver_status_watchdog_ms=1000,
            session_cleanup_timeout_ms=1,
        )
    )
    driver = state()
    pilot = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, pilot)
    task = await acquire_task(server, pilot)
    await asyncio.sleep(0)
    session_id = await answer_driver_start(server, driver)
    await task

    server._mark_connection_disappeared(pilot)
    await asyncio.sleep(0.002)
    await server._cleanup_disappeared_endpoint_sessions()

    assert session_id not in server.sessions
    assert driver.websocket.sent[-2]["type"] == TYPE_SESSION_END
    assert driver.websocket.sent[-1]["type"] == TYPE_SESSION_ENDED
    assert driver.websocket.sent[-1]["payload"]["reason"] == {"code": "session.ended.endpoint_disappeared"}


def test_pilot_reconnect_hello_resumes_active_session():
    asyncio.run(_pilot_reconnect_hello_resumes_active_session())


async def _pilot_reconnect_hello_resumes_active_session():
    server = ItoServer(ServerConfig(request_timeout_ms=1000, driver_status_watchdog_ms=1000))
    driver = state()
    pilot = state()
    reconnected = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, pilot)
    task = await acquire_task(server, pilot)
    await asyncio.sleep(0)
    session_id = await answer_driver_start(server, driver)
    await task

    server._mark_connection_disappeared(pilot)
    await hello_pilot(server, reconnected, session_id=session_id)

    resumed = reconnected.websocket.sent[-1]
    assert resumed["type"] == TYPE_CONNECTION_HELLO_RESULT
    assert resumed["payload"] == {
        "ok": True,
        "value": {
            "protocolVersion": "ito.v1",
            "role": ROLE_PILOT_CLIENT,
            "sessionResumed": True,
            "sessionConfig": server.config.session_config_payload(),
        },
    }
    assert server.sessions[session_id].pilot_connection is reconnected
    assert server.sessions[session_id].endpoint_missing_since is None


def test_pilot_reconnect_hello_rejects_missing_session():
    asyncio.run(_pilot_reconnect_hello_rejects_missing_session())


async def _pilot_reconnect_hello_rejects_missing_session():
    server = ItoServer(ServerConfig())
    pilot = state()

    await hello_pilot(server, pilot, session_id="session-missing")

    assert pilot.websocket.sent[-1]["type"] == TYPE_CONNECTION_HELLO_RESULT
    assert pilot.websocket.sent[-1]["payload"] == {
        "ok": False,
        "reason": {"code": "session.resume_unavailable"},
    }
