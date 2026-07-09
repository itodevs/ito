"""Ito Droid ROS driver implementation."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Mapping

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from server.ito.protocol import (
    ROLE_ROBOT_DRIVER,
    ROBOT_STATUS_AVAILABLE,
    ROBOT_STATUS_UNAVAILABLE,
    ROBOT_TYPE_DROID,
    TYPE_CONNECTION_HELLO,
    TYPE_CONNECTION_HELLO_RESULT,
    TYPE_DRIVER_SESSION_START,
    TYPE_DRIVER_SESSION_START_RESULT,
    TYPE_ROBOT_STATUS,
    TYPE_SESSION_END,
    TYPE_SESSION_END_RESULT,
    TYPE_SESSION_ENDED,
    DisplayReason,
    make_envelope,
    pack_envelope,
    result_error,
    result_ok,
    unpack_envelope,
)

from .config import ItoDroidConfig
from .control import CameraPanController
from .media import CameraMediaPublisher
from .ros_io import CameraFrame, CameraFrameSink, LoggingServoPublisher, RosBridge, ServoPublisher

LOGGER = logging.getLogger(__name__)


class ItoDroidDriver(CameraFrameSink):
    """ROS-backed Ito Droid driver with testable control behavior."""

    def __init__(
        self,
        config: ItoDroidConfig,
        *,
        servo_publisher: ServoPublisher | None = None,
        media_publisher: CameraMediaPublisher | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self.config = config
        self.clock = clock
        self.controller = CameraPanController(config)
        self.servo_publisher = servo_publisher or LoggingServoPublisher()
        self.media_publisher = media_publisher or CameraMediaPublisher()
        self.session_id: str | None = None
        self.session_config: dict[str, object] | None = None
        self.camera_ready = False
        self.servo_ready = True

    @property
    def available(self) -> bool:
        return self.camera_ready and self.servo_ready and self.session_id is None

    def status_payload(self) -> dict[str, object]:
        if self.available:
            return {
                "name": self.config.name,
                "type": ROBOT_TYPE_DROID,
                "status": ROBOT_STATUS_AVAILABLE,
            }
        detail = "ito_droid.session_active"
        if not self.camera_ready:
            detail = "ito_droid.camera_feed_missing"
        elif not self.servo_ready:
            detail = "ito_droid.servo_unavailable"
        return {
            "name": self.config.name,
            "type": ROBOT_TYPE_DROID,
            "status": ROBOT_STATUS_UNAVAILABLE,
            "availabilityDetail": {"code": detail},
        }

    def receive_camera_frame(self, frame: CameraFrame) -> None:
        self.camera_ready = True
        self.media_publisher.publish_frame(frame)

    def receive_pilot_input_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self.controller.receive_snapshot(snapshot, self.clock())

    def neutralize_servo(self) -> None:
        angle = self.controller.neutralize()
        self.servo_publisher.publish_angle(angle)

    def process_control_tick(self, dt_seconds: float) -> float:
        angle = self.controller.tick(self.clock(), dt_seconds)
        self.servo_publisher.publish_angle(angle)
        return angle

    async def run_forever(self) -> None:
        delay_seconds = self.config.reconnect_initial_delay_ms / 1000
        max_delay_seconds = self.config.reconnect_max_delay_ms / 1000
        while True:
            try:
                await self.run_once()
                delay_seconds = self.config.reconnect_initial_delay_ms / 1000
            except (ConnectionClosed, OSError) as exc:
                LOGGER.warning("Ito Droid control connection lost: %s", exc)
            await asyncio.sleep(delay_seconds)
            delay_seconds = min(max_delay_seconds, delay_seconds * 2)

    async def run_once(self) -> None:
        async with connect(self.config.server_url) as websocket:
            hello = make_envelope(
                TYPE_CONNECTION_HELLO,
                {"role": ROLE_ROBOT_DRIVER, "robotId": self.config.robot_id},
                robot_id=self.config.robot_id,
            )
            await websocket.send(pack_envelope(hello))
            result = unpack_envelope(await websocket.recv())
            if result["type"] != TYPE_CONNECTION_HELLO_RESULT or not result["payload"].get("ok"):
                raise RuntimeError(f"Ito Droid hello rejected: {result['payload']}")

            tasks = [
                asyncio.create_task(self._status_loop(websocket)),
                asyncio.create_task(self._control_loop()),
            ]
            try:
                async for frame in websocket:
                    if not isinstance(frame, bytes):
                        LOGGER.warning("Ignoring non-binary Ito control frame")
                        continue
                    await self.handle_message(websocket, unpack_envelope(frame))
            finally:
                for task in tasks:
                    task.cancel()
                self._clear_session()

    async def _status_loop(self, websocket: Any) -> None:
        while True:
            await self.send_status(websocket)
            await asyncio.sleep(self.config.status_interval_ms / 1000)

    async def _control_loop(self) -> None:
        period = 1 / self.config.control_tick_hz
        while True:
            started = self.clock()
            if self.session_id is not None:
                self.process_control_tick(period)
            elapsed = self.clock() - started
            await asyncio.sleep(max(0, period - elapsed))

    async def send_status(self, websocket: Any) -> None:
        await websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_ROBOT_STATUS,
                    self.status_payload(),
                    robot_id=self.config.robot_id,
                    session_id=self.session_id,
                )
            )
        )

    async def handle_message(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        message_type = envelope["type"]
        if message_type == TYPE_DRIVER_SESSION_START:
            await self.handle_session_start(websocket, envelope)
        elif message_type == TYPE_SESSION_END:
            await self.handle_session_end(websocket, envelope)
        elif message_type == TYPE_SESSION_ENDED:
            LOGGER.info("Ito Droid session ended: %s", envelope["payload"])
            self._clear_session()
        else:
            LOGGER.info("Ito Droid ignoring unsupported message type %s", message_type)

    async def handle_session_start(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        requested_session_id = envelope.get("sessionId") or envelope["payload"].get("sessionId")
        if not isinstance(requested_session_id, str) or not requested_session_id:
            await self._send_start_result(
                websocket,
                envelope,
                result_error(DisplayReason(code="driver.session_start.invalid_session")),
            )
            return
        if self.session_id is not None:
            await self._send_start_result(
                websocket,
                envelope,
                result_error(DisplayReason(code="driver.session_start.already_active")),
            )
            return
        if not self.camera_ready:
            await self._send_start_result(
                websocket,
                envelope,
                result_error(DisplayReason(code="ito_droid.camera_feed_missing")),
            )
            return
        try:
            self.neutralize_servo()
        except Exception as exc:  # pragma: no cover - hardware adapter failure path
            LOGGER.error("Ito Droid failed to neutralize camera-pan servo: %s", exc)
            self.servo_ready = False
            await self._send_start_result(
                websocket,
                envelope,
                result_error(
                    DisplayReason(code="ito_droid.servo_neutralization_failed", text=str(exc))
                ),
            )
            return

        self.session_id = requested_session_id
        self.session_config = dict(envelope["payload"].get("sessionConfig") or {})
        self.media_publisher.start(self.session_id)
        await self._send_start_result(
            websocket,
            envelope,
            result_ok({"sessionId": self.session_id}),
        )

    async def handle_session_end(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        ended_session_id = envelope.get("sessionId") or self.session_id
        clean = bool(envelope["payload"].get("clean"))
        self._clear_session(neutralize=clean)
        await websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_SESSION_END_RESULT,
                    result_ok({"sessionId": ended_session_id}),
                    reply_to_message_id=envelope["messageId"],
                    robot_id=self.config.robot_id,
                    session_id=ended_session_id if isinstance(ended_session_id, str) else None,
                )
            )
        )

    async def _send_start_result(
        self,
        websocket: Any,
        request: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> None:
        session_id = request.get("sessionId") or request["payload"].get("sessionId")
        await websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_DRIVER_SESSION_START_RESULT,
                    payload,
                    reply_to_message_id=request["messageId"],
                    robot_id=self.config.robot_id,
                    session_id=session_id if isinstance(session_id, str) else None,
                )
            )
        )

    def _clear_session(self, *, neutralize: bool = False) -> None:
        self.media_publisher.stop()
        self.session_id = None
        self.session_config = None
        if neutralize:
            try:
                self.neutralize_servo()
            except Exception as exc:  # pragma: no cover - hardware adapter failure path
                LOGGER.error("Ito Droid failed clean session-end neutralization: %s", exc)


async def run(config: ItoDroidConfig | None = None) -> None:
    resolved_config = config or ItoDroidConfig.from_env()
    driver = ItoDroidDriver(resolved_config)
    ros_bridge = RosBridge(resolved_config, driver, clock=driver.clock)
    driver.servo_publisher = ros_bridge
    ros_bridge.start()
    ros_task = asyncio.create_task(_ros_spin_loop(ros_bridge))
    try:
        await driver.run_forever()
    finally:
        ros_task.cancel()
        ros_bridge.close()


async def _ros_spin_loop(ros_bridge: RosBridge) -> None:
    while True:
        ros_bridge.spin_once(timeout_seconds=0.0)
        await asyncio.sleep(0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
