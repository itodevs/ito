"""Lightweight mock remote robot driver."""

from __future__ import annotations

import asyncio
import json
import logging
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
    TYPE_WEBRTC_ANSWER,
    TYPE_WEBRTC_OFFER,
    WEBRTC_PATH_CAMERA_MEDIA,
    WEBRTC_PATH_PILOT_INPUT,
    make_envelope,
    pack_envelope,
    result_error,
    result_ok,
    unpack_envelope,
)

from .camera import VideoFileCamera
from .config import MockRobotConfig
from .webrtc import CameraMediaWebRtcPublisher, PilotInputWebRtcReceiver

LOGGER = logging.getLogger(__name__)


class MockRobotDriver:
    def __init__(self, config: MockRobotConfig, *, camera_media_webrtc: Any | None = None) -> None:
        self.config = config
        self.control_active = False
        self.camera = (
            VideoFileCamera(
                config.camera_video_path,
                chunk_size=config.camera_chunk_size,
                loop=config.camera_loop,
            )
            if config.camera_video_path
            else None
        )
        self.pilot_input_webrtc: PilotInputWebRtcReceiver | None = None
        self.camera_media_webrtc = camera_media_webrtc

    @property
    def ready(self) -> bool:
        return self.camera is not None

    async def run_forever(self) -> None:
        delay_seconds = self.config.reconnect_initial_delay_ms / 1000
        maximum = self.config.reconnect_max_delay_ms / 1000
        while True:
            try:
                await self.run_once()
                delay_seconds = self.config.reconnect_initial_delay_ms / 1000
            except (ConnectionClosed, OSError) as exc:
                LOGGER.warning("Remote robot connection lost: %s", exc)
            await asyncio.sleep(delay_seconds)
            delay_seconds = min(maximum, delay_seconds * 2)

    async def run_once(self) -> None:
        if self.camera is not None:
            self.camera.validate()
        async with connect(self.config.ito_url) as websocket:
            hello = make_envelope(
                TYPE_CONNECTION_HELLO,
                {"role": ROLE_REMOTE_ROBOT_DRIVER, "ready": self.ready},
            )
            await websocket.send(pack_envelope(hello))
            result = unpack_envelope(await websocket.recv())
            if result["type"] != TYPE_CONNECTION_HELLO_RESULT or not result["payload"].get("ok"):
                raise RuntimeError(f"remote robot hello rejected: {result['payload']}")
            try:
                async for frame in websocket:
                    if isinstance(frame, bytes):
                        await self.handle_message(websocket, unpack_envelope(frame))
            finally:
                await self._clear_control()

    async def handle_message(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        message_type = envelope["type"]
        if message_type == TYPE_DRIVER_CONTROL_START:
            await self.handle_control_start(websocket, envelope)
        elif message_type == TYPE_DRIVER_CONTROL_STOP:
            await self.handle_control_stop(websocket, envelope)
        elif message_type == TYPE_WEBRTC_OFFER:
            await self.handle_webrtc_offer(websocket, envelope)
        elif message_type == TYPE_WEBRTC_ANSWER:
            await self.handle_webrtc_answer(envelope)

    async def handle_control_start(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        if self.control_active:
            await self._send_result(
                websocket,
                envelope,
                TYPE_DRIVER_CONTROL_START_RESULT,
                result_error(DisplayReason(code="control.already_active")),
            )
            return
        if self.camera is None:
            await self._send_result(
                websocket,
                envelope,
                TYPE_DRIVER_CONTROL_START_RESULT,
                result_error(DisplayReason(code="mock_robot.camera_video_required")),
            )
            return
        try:
            self.camera.open()
        except (OSError, ValueError) as exc:
            await self._send_result(
                websocket,
                envelope,
                TYPE_DRIVER_CONTROL_START_RESULT,
                result_error(DisplayReason(code="mock_robot.camera_video_unavailable", text=str(exc))),
            )
            return
        self.control_active = True
        await self._send_result(
            websocket, envelope, TYPE_DRIVER_CONTROL_START_RESULT, result_ok()
        )
        await self._start_camera_media(websocket)

    async def handle_control_stop(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        await self._clear_control()
        await self._send_result(
            websocket, envelope, TYPE_DRIVER_CONTROL_STOP_RESULT, result_ok()
        )

    async def handle_webrtc_offer(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        sdp = envelope["payload"].get("sdp")
        if envelope["payload"].get("path") != WEBRTC_PATH_PILOT_INPUT or not isinstance(sdp, str):
            return
        if self.pilot_input_webrtc is None:
            self.pilot_input_webrtc = PilotInputWebRtcReceiver(self.receive_pilot_input_snapshot)
        answer = await self.pilot_input_webrtc.accept_offer(sdp=sdp)
        await websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_WEBRTC_ANSWER,
                    {"path": WEBRTC_PATH_PILOT_INPUT, "sdp": answer},
                    reply_to_message_id=envelope["messageId"],
                )
            )
        )

    async def handle_webrtc_answer(self, envelope: Mapping[str, Any]) -> None:
        sdp = envelope["payload"].get("sdp")
        if envelope["payload"].get("path") != WEBRTC_PATH_CAMERA_MEDIA or not isinstance(sdp, str):
            return
        if self.camera_media_webrtc is not None:
            await self.camera_media_webrtc.accept_answer(sdp=sdp)

    async def _start_camera_media(self, websocket: Any) -> None:
        if not self.control_active or self.camera is None:
            return
        if self.camera_media_webrtc is None:
            self.camera_media_webrtc = CameraMediaWebRtcPublisher()
        sdp = await self.camera_media_webrtc.create_offer(
            video_path=self.camera.path,
            loop=self.camera.loop,
        )
        await websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_WEBRTC_OFFER,
                    {"path": WEBRTC_PATH_CAMERA_MEDIA, "sdp": sdp},
                )
            )
        )

    def receive_pilot_input_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        LOGGER.info("pilot_input_snapshot %s", json.dumps(dict(snapshot), sort_keys=True))

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

    async def _clear_control(self) -> None:
        self.control_active = False
        if self.camera is not None:
            self.camera.close()
        if self.pilot_input_webrtc is not None:
            await self.pilot_input_webrtc.close()
        if self.camera_media_webrtc is not None:
            await self.camera_media_webrtc.close()


async def run(config: MockRobotConfig | None = None) -> None:
    await MockRobotDriver(config or MockRobotConfig.from_env()).run_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
