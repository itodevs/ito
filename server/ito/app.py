"""Ito Server WebSocket control-plane implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from time import monotonic
from typing import Any
from uuid import uuid4

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from .config import ServerConfig
from .protocol import (
    DisplayReason,
    PROTOCOL_VERSION,
    ProtocolError,
    ROLE_PILOT_CLIENT,
    ROLE_ROBOT_DRIVER,
    ROBOT_STATUS_AVAILABLE,
    ROBOT_STATUS_OCCUPIED,
    ROBOT_STATUS_UNAVAILABLE,
    ROBOT_STATUSES,
    ROBOT_TYPES,
    TYPE_CATALOG_GET,
    TYPE_CATALOG_GET_RESULT,
    TYPE_DRIVER_SESSION_START,
    TYPE_DRIVER_SESSION_START_RESULT,
    TYPE_SESSION_ACQUIRE,
    TYPE_SESSION_ACQUIRE_RESULT,
    TYPE_SESSION_END,
    TYPE_SESSION_END_RESULT,
    TYPE_SESSION_ENDED,
    TYPE_CONNECTION_HELLO,
    TYPE_CONNECTION_HELLO_RESULT,
    TYPE_ROBOT_STATUS,
    make_envelope,
    pack_envelope,
    result_error,
    result_ok,
    unpack_envelope,
)

LOGGER = logging.getLogger(__name__)

SESSION_STATE_STARTING = "starting"
SESSION_STATE_ACTIVE = "active"
SESSION_STATE_ENDED = "ended"


@dataclass(eq=False)
class ConnectionState:
    websocket: ServerConnection
    role: str | None = None
    robot_id: str | None = None
    session_id: str | None = None


@dataclass
class DriverRecord:
    robot_id: str
    connection: ConnectionState | None = None
    name: str | None = None
    robot_type: str | None = None
    driver_status: str = ROBOT_STATUS_UNAVAILABLE
    availability_detail: dict[str, str] | None = None
    last_status_at: float | None = None
    duplicate: bool = False
    occupied: bool = False

    def catalog_entry(self, now: float, watchdog_seconds: float) -> dict[str, Any]:
        status = self.effective_status(now, watchdog_seconds)
        entry: dict[str, Any] = {
            "robotId": self.robot_id,
            "name": self.name or self.robot_id,
            "type": self.robot_type or "Droid",
            "status": status,
        }
        if self.availability_detail:
            entry["availabilityDetail"] = self.availability_detail
        elif status == ROBOT_STATUS_UNAVAILABLE:
            entry["availabilityDetail"] = {"code": "robot.unavailable"}
        return entry

    def effective_status(self, now: float, watchdog_seconds: float) -> str:
        if self.duplicate:
            return ROBOT_STATUS_UNAVAILABLE
        if self.occupied:
            return ROBOT_STATUS_OCCUPIED
        if self.connection is None or self.last_status_at is None:
            return ROBOT_STATUS_UNAVAILABLE
        if now - self.last_status_at > watchdog_seconds:
            return ROBOT_STATUS_UNAVAILABLE
        return self.driver_status


@dataclass
class SessionRecord:
    session_id: str
    robot_id: str
    pilot_connection: ConnectionState | None
    driver_connection: ConnectionState | None
    session_config: dict[str, object]
    state: str = SESSION_STATE_STARTING
    created_at: float = field(default_factory=monotonic)
    endpoint_missing_since: float | None = None
    ended_reason: dict[str, str] | None = None
    ended_by: str | None = None
    clean: bool = False

    def note_endpoint_missing(self) -> None:
        if self.endpoint_missing_since is None:
            self.endpoint_missing_since = monotonic()

    def note_endpoint_present(self) -> None:
        if self.pilot_connection is not None and self.driver_connection is not None:
            self.endpoint_missing_since = None


class ItoServer:
    def __init__(self, config: ServerConfig | None = None) -> None:
        self.config = config or ServerConfig.from_env()
        self.connections: set[ConnectionState] = set()
        self.drivers: dict[str, DriverRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self._pending_requests: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._acquisition_lock = asyncio.Lock()
        self._watchdog_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    @property
    def watchdog_seconds(self) -> float:
        return self.config.driver_status_watchdog_ms / 1000

    @property
    def request_timeout_seconds(self) -> float:
        return self.config.request_timeout_ms / 1000

    @property
    def session_cleanup_seconds(self) -> float:
        return self.config.session_cleanup_timeout_ms / 1000

    async def serve_forever(self) -> None:
        LOGGER.info("Starting Ito Server on %s:%s", self.config.host, self.config.port)
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        self._cleanup_task = asyncio.create_task(self._session_cleanup_loop())
        try:
            async with serve(self._handle_connection, self.config.host, self.config.port):
                await asyncio.Future()
        finally:
            self._watchdog_task.cancel()
            self._cleanup_task.cancel()

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        state = ConnectionState(websocket=websocket)
        self.connections.add(state)
        try:
            async for frame in websocket:
                await self._handle_frame(state, frame)
        except ConnectionClosed:
            pass
        finally:
            self.connections.discard(state)
            if state.role == ROLE_ROBOT_DRIVER and state.robot_id:
                record = self.drivers.get(state.robot_id)
                if record and record.connection is state:
                    record.connection = None
                    record.driver_status = ROBOT_STATUS_UNAVAILABLE
                    record.availability_detail = {"code": "robot.unavailable.driver_disconnected"}
            self._mark_connection_disappeared(state)

    async def _handle_frame(self, state: ConnectionState, frame: bytes | str) -> None:
        if not isinstance(frame, bytes):
            await self._send_error(state, TYPE_CONNECTION_HELLO_RESULT, None, "protocol.invalid_frame")
            return
        try:
            envelope = unpack_envelope(frame)
        except ProtocolError as exc:
            LOGGER.warning("Rejecting invalid Ito envelope: %s", exc)
            await self._send_error(state, TYPE_CONNECTION_HELLO_RESULT, None, "protocol.invalid_message")
            return

        if state.role is None and envelope["type"] != TYPE_CONNECTION_HELLO:
            await self._send_error(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], "connection.hello_required")
            return

        if envelope["type"] == TYPE_CONNECTION_HELLO:
            await self._handle_hello(state, envelope)
        elif envelope["type"] in {TYPE_DRIVER_SESSION_START_RESULT, TYPE_SESSION_END_RESULT}:
            self._handle_response(envelope)
        elif envelope["type"] == TYPE_ROBOT_STATUS:
            self._handle_robot_status(state, envelope)
        elif envelope["type"] == TYPE_CATALOG_GET:
            await self._handle_catalog_get(state, envelope)
        elif envelope["type"] == TYPE_SESSION_ACQUIRE:
            await self._handle_session_acquire(state, envelope)
        elif envelope["type"] == TYPE_SESSION_END:
            await self._handle_session_end(state, envelope)
        else:
            result_type = {
                TYPE_SESSION_ACQUIRE: TYPE_SESSION_ACQUIRE_RESULT,
                TYPE_SESSION_END: TYPE_SESSION_END_RESULT,
            }.get(envelope["type"], TYPE_CONNECTION_HELLO_RESULT)
            await self._send_result(
                state,
                result_type,
                envelope["messageId"],
                result_error(DisplayReason(code="protocol.unsupported_message")),
            )

    async def _handle_hello(self, state: ConnectionState, envelope: dict[str, Any]) -> None:
        payload = envelope["payload"]
        role = payload.get("role")
        if role == ROLE_ROBOT_DRIVER:
            robot_id = payload.get("robotId") or envelope.get("robotId")
            if not isinstance(robot_id, str) or not robot_id:
                await self._send_error(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], "connection.robot_id_required")
                return
            state.role = role
            state.robot_id = robot_id
            record = self.drivers.setdefault(robot_id, DriverRecord(robot_id=robot_id))
            if record.connection is not None and record.connection is not state:
                record.duplicate = True
                record.connection = None
                LOGGER.error("Duplicate robotId reported: %s", robot_id)
            elif not record.duplicate:
                record.connection = state
                session = self._active_session_for_robot(robot_id)
                if session and session.driver_connection is None:
                    session.driver_connection = state
                    state.session_id = session.session_id
                    session.note_endpoint_present()
            await self._send_result(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], result_ok({"protocolVersion": PROTOCOL_VERSION, "role": role}))
            return
        if role == ROLE_PILOT_CLIENT:
            requested_session_id = payload.get("sessionId")
            if requested_session_id is not None:
                if not isinstance(requested_session_id, str):
                    await self._send_error(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], "connection.invalid_session")
                    return
                session = self.sessions.get(requested_session_id)
                if session is None or session.state != SESSION_STATE_ACTIVE:
                    await self._send_error(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], "session.resume_unavailable")
                    return
                state.role = role
                state.session_id = requested_session_id
                session.pilot_connection = state
                session.note_endpoint_present()
                await self._send_result(
                    state,
                    TYPE_CONNECTION_HELLO_RESULT,
                    envelope["messageId"],
                    result_ok(
                        {
                            "protocolVersion": PROTOCOL_VERSION,
                            "role": role,
                            "sessionResumed": True,
                            "sessionConfig": session.session_config,
                        }
                    ),
                )
                return
            state.role = role
            await self._send_result(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], result_ok({"protocolVersion": PROTOCOL_VERSION, "role": role}))
            return
        await self._send_error(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], "connection.invalid_role")

    def _handle_response(self, envelope: dict[str, Any]) -> None:
        reply_to = envelope.get("replyToMessageId")
        if not isinstance(reply_to, str):
            LOGGER.warning("Ignoring response without replyToMessageId: %s", envelope["type"])
            return
        pending = self._pending_requests.get(reply_to)
        if pending is None or pending.done():
            LOGGER.warning("Ignoring response for unknown request: %s", reply_to)
            return
        pending.set_result(envelope)

    def _handle_robot_status(self, state: ConnectionState, envelope: dict[str, Any]) -> None:
        if state.role != ROLE_ROBOT_DRIVER or not state.robot_id:
            LOGGER.warning("Ignoring robot.status from non-driver connection")
            return
        payload = envelope["payload"]
        if payload.get("status") not in ROBOT_STATUSES or payload.get("type") not in ROBOT_TYPES or not isinstance(payload.get("name"), str):
            LOGGER.warning("Ignoring invalid robot.status from %s", state.robot_id)
            return
        record = self.drivers.setdefault(state.robot_id, DriverRecord(robot_id=state.robot_id))
        if record.duplicate:
            return
        record.connection = state
        record.name = payload["name"]
        record.robot_type = payload["type"]
        record.driver_status = payload["status"]
        detail = payload.get("availabilityDetail")
        record.availability_detail = detail if isinstance(detail, dict) else None
        record.last_status_at = monotonic()

    async def _handle_catalog_get(self, state: ConnectionState, envelope: dict[str, Any]) -> None:
        if state.role != ROLE_PILOT_CLIENT:
            await self._send_error(state, TYPE_CATALOG_GET_RESULT, envelope["messageId"], "catalog.pilot_client_required")
            return
        include_unavailable = envelope["payload"].get("includeUnavailable", True)
        now = monotonic()
        robots = [r.catalog_entry(now, self.watchdog_seconds) for r in self.drivers.values()]
        if not include_unavailable:
            robots = [r for r in robots if r["status"] != ROBOT_STATUS_UNAVAILABLE]
        await self._send_result(state, TYPE_CATALOG_GET_RESULT, envelope["messageId"], result_ok({"robots": robots}))

    async def _handle_session_acquire(self, state: ConnectionState, envelope: dict[str, Any]) -> None:
        if state.role != ROLE_PILOT_CLIENT:
            await self._send_error(state, TYPE_SESSION_ACQUIRE_RESULT, envelope["messageId"], "session.acquire.pilot_client_required")
            return
        robot_id = envelope["payload"].get("robotId") or envelope.get("robotId")
        if not isinstance(robot_id, str) or not robot_id:
            await self._send_error(state, TYPE_SESSION_ACQUIRE_RESULT, envelope["messageId"], "session.acquire.robot_id_required")
            return

        async with self._acquisition_lock:
            record = self.drivers.get(robot_id)
            now = monotonic()
            if record is None or record.effective_status(now, self.watchdog_seconds) != ROBOT_STATUS_AVAILABLE or record.connection is None:
                await self._send_error(state, TYPE_SESSION_ACQUIRE_RESULT, envelope["messageId"], "session.acquire.robot_unavailable")
                return

            record.occupied = True
            session_id = self._make_session_id()
            session_config = self.config.session_config_payload()
            session = SessionRecord(
                session_id=session_id,
                robot_id=robot_id,
                pilot_connection=state,
                driver_connection=record.connection,
                session_config=session_config,
            )
            self.sessions[session_id] = session

            start_result = await self._request_driver_session_start(record.connection, robot_id, session_id, session_config)
            if not start_result["payload"].get("ok"):
                self._release_failed_acquisition(session)
                await self._send_result(state, TYPE_SESSION_ACQUIRE_RESULT, envelope["messageId"], start_result["payload"])
                return

            value = start_result["payload"].get("value", {})
            if value.get("sessionId") != session_id:
                self._release_failed_acquisition(session)
                await self._send_error(state, TYPE_SESSION_ACQUIRE_RESULT, envelope["messageId"], "driver.session_start.invalid_session")
                return

            session.state = SESSION_STATE_ACTIVE
            state.session_id = session_id
            record.connection.session_id = session_id
            await self._send_result(
                state,
                TYPE_SESSION_ACQUIRE_RESULT,
                envelope["messageId"],
                result_ok(
                    {
                        "sessionId": session_id,
                        "robotId": robot_id,
                        "sessionConfig": session_config,
                    }
                ),
            )

    async def _request_driver_session_start(
        self,
        driver: ConnectionState,
        robot_id: str,
        session_id: str,
        session_config: dict[str, object],
    ) -> dict[str, Any]:
        request = make_envelope(
            TYPE_DRIVER_SESSION_START,
            {"sessionId": session_id, "sessionConfig": session_config},
            robot_id=robot_id,
            session_id=session_id,
        )
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending_requests[request["messageId"]] = future
        try:
            await driver.websocket.send(pack_envelope(request))
            return await asyncio.wait_for(future, timeout=self.request_timeout_seconds)
        except TimeoutError:
            return make_envelope(
                TYPE_DRIVER_SESSION_START_RESULT,
                result_error(DisplayReason(code="request.timeout")),
                reply_to_message_id=request["messageId"],
                robot_id=robot_id,
                session_id=session_id,
            )
        finally:
            self._pending_requests.pop(request["messageId"], None)

    def _release_failed_acquisition(self, session: SessionRecord) -> None:
        self.sessions.pop(session.session_id, None)
        record = self.drivers.get(session.robot_id)
        if record:
            record.occupied = False
        if session.pilot_connection and session.pilot_connection.session_id == session.session_id:
            session.pilot_connection.session_id = None
        if session.driver_connection and session.driver_connection.session_id == session.session_id:
            session.driver_connection.session_id = None

    async def _handle_session_end(self, state: ConnectionState, envelope: dict[str, Any]) -> None:
        session_id = envelope.get("sessionId") or state.session_id
        if not isinstance(session_id, str) or session_id not in self.sessions:
            await self._send_error(state, TYPE_SESSION_END_RESULT, envelope["messageId"], "session.end.unknown_session")
            return
        session = self.sessions[session_id]
        if session.state == SESSION_STATE_ENDED:
            await self._send_result(state, TYPE_SESSION_END_RESULT, envelope["messageId"], result_ok({"sessionId": session_id}))
            return
        if state not in {session.pilot_connection, session.driver_connection}:
            await self._send_error(state, TYPE_SESSION_END_RESULT, envelope["messageId"], "session.end.endpoint_required")
            return

        reason = envelope["payload"].get("reason")
        if not isinstance(reason, dict):
            reason = {"code": "session.ended.requested"}
        clean = bool(envelope["payload"].get("clean", False))
        ended_by = state.role or "server"

        await self._send_result(state, TYPE_SESSION_END_RESULT, envelope["messageId"], result_ok({"sessionId": session_id}))
        await self._end_session(session, reason=reason, ended_by=ended_by, clean=clean, request_driver_end=state is not session.driver_connection)

    async def _end_session(
        self,
        session: SessionRecord,
        *,
        reason: dict[str, str],
        ended_by: str,
        clean: bool,
        request_driver_end: bool = True,
    ) -> None:
        if session.state == SESSION_STATE_ENDED:
            return
        session.state = SESSION_STATE_ENDED
        session.ended_reason = reason
        session.ended_by = ended_by
        session.clean = clean
        record = self.drivers.get(session.robot_id)
        if record:
            record.occupied = False
        if session.pilot_connection and session.pilot_connection.session_id == session.session_id:
            session.pilot_connection.session_id = None
        if session.driver_connection and session.driver_connection.session_id == session.session_id:
            session.driver_connection.session_id = None

        if request_driver_end and session.driver_connection is not None:
            await self._send_driver_session_end(session, reason, clean)

        ended_payload = {"reason": reason, "endedBy": ended_by, "clean": clean}
        await self._send_session_ended(session.pilot_connection, session, ended_payload)
        await self._send_session_ended(session.driver_connection, session, ended_payload)

    async def _send_driver_session_end(self, session: SessionRecord, reason: dict[str, str], clean: bool) -> None:
        if session.driver_connection is None:
            return
        await session.driver_connection.websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_SESSION_END,
                    {"reason": reason, "clean": clean},
                    robot_id=session.robot_id,
                    session_id=session.session_id,
                )
            )
        )

    async def _send_session_ended(
        self, state: ConnectionState | None, session: SessionRecord, payload: dict[str, Any]
    ) -> None:
        if state is None:
            return
        await state.websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_SESSION_ENDED,
                    payload,
                    robot_id=session.robot_id,
                    session_id=session.session_id,
                )
            )
        )

    async def _send_error(self, state: ConnectionState, message_type: str, reply_to: str | None, code: str) -> None:
        await self._send_result(state, message_type, reply_to, result_error(DisplayReason(code=code)))

    async def _send_result(self, state: ConnectionState, message_type: str, reply_to: str | None, payload: dict[str, Any]) -> None:
        await state.websocket.send(pack_envelope(make_envelope(message_type, payload, reply_to_message_id=reply_to, robot_id=state.robot_id, session_id=state.session_id)))

    def _make_session_id(self) -> str:
        return f"session-{uuid4()}"

    def _active_session_for_robot(self, robot_id: str) -> SessionRecord | None:
        for session in self.sessions.values():
            if session.robot_id == robot_id and session.state != SESSION_STATE_ENDED:
                return session
        return None

    def _mark_connection_disappeared(self, state: ConnectionState) -> None:
        for session in self.sessions.values():
            changed = False
            if session.pilot_connection is state:
                session.pilot_connection = None
                changed = True
            if session.driver_connection is state:
                session.driver_connection = None
                changed = True
            if changed and session.state != SESSION_STATE_ENDED:
                session.note_endpoint_missing()

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(self.watchdog_seconds / 2)
            now = monotonic()
            for record in self.drivers.values():
                if record.effective_status(now, self.watchdog_seconds) == ROBOT_STATUS_UNAVAILABLE and record.connection is not None and record.last_status_at is not None and now - record.last_status_at > self.watchdog_seconds:
                    record.driver_status = ROBOT_STATUS_UNAVAILABLE
                    record.availability_detail = {"code": "robot.unavailable.driver_status_timeout"}

    async def _session_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.session_cleanup_seconds / 2)
            await self._cleanup_disappeared_endpoint_sessions()

    async def _cleanup_disappeared_endpoint_sessions(self) -> None:
        now = monotonic()
        for session in list(self.sessions.values()):
            if session.state == SESSION_STATE_ENDED or session.endpoint_missing_since is None:
                continue
            if now - session.endpoint_missing_since >= self.session_cleanup_seconds:
                await self._end_session(
                    session,
                    reason={"code": "session.ended.endpoint_disappeared"},
                    ended_by="server",
                    clean=False,
                    request_driver_end=True,
                )
                self.sessions.pop(session.session_id, None)


async def run(config: ServerConfig | None = None) -> None:
    await ItoServer(config).serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
