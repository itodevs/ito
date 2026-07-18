"""Ito Droid lightweight remote-driver lifecycle and robot-local safety."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Mapping

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from server.ito.protocol import (
    DisplayReason,
    ROLE_REMOTE_ROBOT_DRIVER,
    TYPE_CONNECTION_HELLO,
    TYPE_CONNECTION_HELLO_RESULT,
    TYPE_DRIVER_CONTROL_START,
    TYPE_DRIVER_CONTROL_START_RESULT,
    TYPE_DRIVER_CONTROL_STOP,
    TYPE_DRIVER_CONTROL_STOP_RESULT,
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
        self.control_active = False
        self.camera_ready = False
        self.servo_ready = True

    @property
    def ready(self) -> bool:
        return self.camera_ready and self.servo_ready

    def receive_camera_frame(self, frame: CameraFrame) -> None:
        self.camera_ready = True
        self.media_publisher.publish_frame(frame)

    def receive_pilot_input_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self.controller.receive_snapshot(snapshot, self.clock())

    def neutralize_servo(self) -> None:
        self.servo_publisher.publish_angle(self.controller.neutralize())

    def process_control_tick(self, dt_seconds: float) -> float:
        angle = self.controller.tick(self.clock(), dt_seconds)
        self.servo_publisher.publish_angle(angle)
        return angle

    async def run_forever(self) -> None:
        delay = self.config.reconnect_initial_delay_ms / 1000
        maximum = self.config.reconnect_max_delay_ms / 1000
        while True:
            if not self.ready:
                await asyncio.sleep(0.1)
                continue
            try:
                await self.run_once()
                delay = self.config.reconnect_initial_delay_ms / 1000
            except (ConnectionClosed, OSError) as exc:
                LOGGER.warning("Ito Droid connection lost: %s", exc)
            await asyncio.sleep(delay)
            delay = min(maximum, delay * 2)

    async def run_once(self) -> None:
        async with connect(self.config.ito_url) as websocket:
            hello = make_envelope(
                TYPE_CONNECTION_HELLO,
                {"role": ROLE_REMOTE_ROBOT_DRIVER, "ready": self.ready},
            )
            await websocket.send(pack_envelope(hello))
            response = unpack_envelope(await websocket.recv())
            if response["type"] != TYPE_CONNECTION_HELLO_RESULT or not response["payload"].get("ok"):
                raise RuntimeError(f"Ito Droid hello rejected: {response['payload']}")
            control_task = asyncio.create_task(self._control_loop())
            try:
                async for frame in websocket:
                    if isinstance(frame, bytes):
                        await self.handle_message(websocket, unpack_envelope(frame))
            finally:
                control_task.cancel()
                self._stop_locally()

    async def _control_loop(self) -> None:
        period = 1 / self.config.control_tick_hz
        while True:
            started = self.clock()
            if self.control_active:
                self.process_control_tick(period)
            await asyncio.sleep(max(0, period - (self.clock() - started)))

    async def handle_message(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        if envelope["type"] == TYPE_DRIVER_CONTROL_START:
            await self.handle_control_start(websocket, envelope)
        elif envelope["type"] == TYPE_DRIVER_CONTROL_STOP:
            await self.handle_control_stop(websocket, envelope)

    async def handle_control_start(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        if self.control_active:
            await self._send_result(
                websocket,
                envelope,
                TYPE_DRIVER_CONTROL_START_RESULT,
                result_error(DisplayReason(code="control.already_active")),
            )
            return
        if not self.camera_ready:
            await self._send_result(
                websocket,
                envelope,
                TYPE_DRIVER_CONTROL_START_RESULT,
                result_error(DisplayReason(code="ito_droid.camera_feed_missing")),
            )
            return
        try:
            self.neutralize_servo()
        except Exception as exc:
            self.servo_ready = False
            await self._send_result(
                websocket,
                envelope,
                TYPE_DRIVER_CONTROL_START_RESULT,
                result_error(DisplayReason(code="ito_droid.servo_neutralization_failed", text=str(exc))),
            )
            return
        self.control_active = True
        self.media_publisher.start()
        await self._send_result(
            websocket, envelope, TYPE_DRIVER_CONTROL_START_RESULT, result_ok()
        )

    async def handle_control_stop(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        self._stop_locally()
        await self._send_result(
            websocket, envelope, TYPE_DRIVER_CONTROL_STOP_RESULT, result_ok()
        )

    def _stop_locally(self) -> None:
        self.control_active = False
        self.media_publisher.stop()
        try:
            self.neutralize_servo()
        except Exception as exc:
            LOGGER.error("Ito Droid safe neutralization failed: %s", exc)

    async def _send_result(
        self,
        websocket: Any,
        request: Mapping[str, Any],
        message_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        await websocket.send(
            pack_envelope(
                make_envelope(
                    message_type,
                    payload,
                    reply_to_message_id=request["messageId"],
                )
            )
        )


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
