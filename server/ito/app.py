"""Ito Server WebSocket control-plane implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from time import monotonic
from typing import Any

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
    TYPE_SESSION_ACQUIRE,
    TYPE_SESSION_ACQUIRE_RESULT,
    TYPE_SESSION_END,
    TYPE_SESSION_END_RESULT,
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


class ItoServer:
    def __init__(self, config: ServerConfig | None = None) -> None:
        self.config = config or ServerConfig.from_env()
        self.connections: set[ConnectionState] = set()
        self.drivers: dict[str, DriverRecord] = {}
        self._watchdog_task: asyncio.Task[None] | None = None

    @property
    def watchdog_seconds(self) -> float:
        return self.config.driver_status_watchdog_ms / 1000

    async def serve_forever(self) -> None:
        LOGGER.info("Starting Ito Server on %s:%s", self.config.host, self.config.port)
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        try:
            async with serve(self._handle_connection, self.config.host, self.config.port):
                await asyncio.Future()
        finally:
            self._watchdog_task.cancel()

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
        elif envelope["type"] == TYPE_ROBOT_STATUS:
            self._handle_robot_status(state, envelope)
        elif envelope["type"] == TYPE_CATALOG_GET:
            await self._handle_catalog_get(state, envelope)
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
            await self._send_result(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], result_ok({"protocolVersion": PROTOCOL_VERSION, "role": role}))
            return
        if role == ROLE_PILOT_CLIENT:
            state.role = role
            state.session_id = payload.get("sessionId")
            await self._send_result(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], result_ok({"protocolVersion": PROTOCOL_VERSION, "role": role, "sessionResumed": False} if state.session_id else {"protocolVersion": PROTOCOL_VERSION, "role": role}))
            return
        await self._send_error(state, TYPE_CONNECTION_HELLO_RESULT, envelope["messageId"], "connection.invalid_role")

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

    async def _send_error(self, state: ConnectionState, message_type: str, reply_to: str | None, code: str) -> None:
        await self._send_result(state, message_type, reply_to, result_error(DisplayReason(code=code)))

    async def _send_result(self, state: ConnectionState, message_type: str, reply_to: str | None, payload: dict[str, Any]) -> None:
        await state.websocket.send(pack_envelope(make_envelope(message_type, payload, reply_to_message_id=reply_to, robot_id=state.robot_id, session_id=state.session_id)))

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(self.watchdog_seconds / 2)
            now = monotonic()
            for record in self.drivers.values():
                if record.effective_status(now, self.watchdog_seconds) == ROBOT_STATUS_UNAVAILABLE and record.connection is not None and record.last_status_at is not None and now - record.last_status_at > self.watchdog_seconds:
                    record.driver_status = ROBOT_STATUS_UNAVAILABLE
                    record.availability_detail = {"code": "robot.unavailable.driver_status_timeout"}


async def run(config: ServerConfig | None = None) -> None:
    await ItoServer(config).serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
