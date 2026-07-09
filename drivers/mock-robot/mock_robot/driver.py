"""Mock Robot driver implementation."""

from __future__ import annotations

import asyncio
import json
import logging
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
    TYPE_WEBRTC_ANSWER,
    TYPE_WEBRTC_OFFER,
    WEBRTC_PATH_CAMERA_MEDIA,
    WEBRTC_PATH_PILOT_INPUT,
    DisplayReason,
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
    """A robot-driver test double that speaks Ito v1 control-plane messages."""

    def __init__(self, config: MockRobotConfig, *, camera_media_webrtc: Any | None = None) -> None:
        self.config = config
        self.session_id: str | None = None
        self.session_config: dict[str, object] | None = None
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
    def available(self) -> bool:
        return self.camera is not None

    def status_payload(self) -> dict[str, object]:
        if self.available:
            return {
                "name": self.config.name,
                "type": ROBOT_TYPE_DROID,
                "status": ROBOT_STATUS_AVAILABLE,
            }
        return {
            "name": self.config.name,
            "type": ROBOT_TYPE_DROID,
            "status": ROBOT_STATUS_UNAVAILABLE,
            "availabilityDetail": {"code": "mock_robot.camera_video_required"},
        }

    async def run_forever(self) -> None:
        delay_seconds = self.config.reconnect_initial_delay_ms / 1000
        max_delay_seconds = self.config.reconnect_max_delay_ms / 1000
        while True:
            try:
                await self.run_once()
                delay_seconds = self.config.reconnect_initial_delay_ms / 1000
            except (ConnectionClosed, OSError) as exc:
                LOGGER.warning("Mock Robot control connection lost: %s", exc)
            await asyncio.sleep(delay_seconds)
            delay_seconds = min(max_delay_seconds, delay_seconds * 2)

    async def run_once(self) -> None:
        if self.camera is not None:
            self.camera.validate()
        async with connect(self.config.server_url) as websocket:
            hello = make_envelope(
                TYPE_CONNECTION_HELLO,
                {"role": ROLE_ROBOT_DRIVER, "robotId": self.config.robot_id},
                robot_id=self.config.robot_id,
            )
            await websocket.send(pack_envelope(hello))
            result = unpack_envelope(await websocket.recv())
            if result["type"] != TYPE_CONNECTION_HELLO_RESULT or not result["payload"].get("ok"):
                raise RuntimeError(f"Mock Robot hello rejected: {result['payload']}")

            status_task = asyncio.create_task(self._status_loop(websocket))
            try:
                async for frame in websocket:
                    if not isinstance(frame, bytes):
                        LOGGER.warning("Ignoring non-binary Ito control frame")
                        continue
                    await self.handle_message(websocket, unpack_envelope(frame))
            finally:
                status_task.cancel()
                await self._clear_session()

    async def _status_loop(self, websocket: Any) -> None:
        while True:
            await self.send_status(websocket)
            await asyncio.sleep(self.config.status_interval_ms / 1000)

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
            LOGGER.info("Mock Robot session ended: %s", envelope["payload"])
            await self._clear_session()
        elif message_type == TYPE_WEBRTC_OFFER:
            await self.handle_webrtc_offer(websocket, envelope)
        elif message_type == TYPE_WEBRTC_ANSWER:
            await self.handle_webrtc_answer(envelope)
        else:
            LOGGER.info("Mock Robot ignoring unsupported message type %s", message_type)

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
        if self.camera is None:
            await self._send_start_result(
                websocket,
                envelope,
                result_error(DisplayReason(code="mock_robot.camera_video_required")),
            )
            return
        try:
            self.camera.open()
        except (OSError, ValueError) as exc:
            LOGGER.error("Mock Robot camera input failed: %s", exc)
            await self._send_start_result(
                websocket,
                envelope,
                result_error(
                    DisplayReason(
                        code="mock_robot.camera_video_unavailable",
                        text=str(exc),
                    )
                ),
            )
            return

        self.session_id = requested_session_id
        self.session_config = dict(envelope["payload"].get("sessionConfig") or {})
        LOGGER.info("Mock Robot session started: %s", self.session_id)
        await self._send_start_result(
            websocket,
            envelope,
            result_ok({"sessionId": self.session_id}),
        )
        await self._start_camera_media(websocket)

    async def handle_session_end(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        ended_session_id = envelope.get("sessionId") or self.session_id
        await self._clear_session()
        await websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_SESSION_END_RESULT,
                    result_ok({"sessionId": ended_session_id}),
                    reply_to_message_id=envelope["messageId"],
                    robot_id=self.config.robot_id,
                    session_id=ended_session_id,
                )
            )
        )

    async def handle_webrtc_offer(self, websocket: Any, envelope: Mapping[str, Any]) -> None:
        if envelope["payload"].get("path") != WEBRTC_PATH_PILOT_INPUT:
            LOGGER.info("Mock Robot ignoring unsupported WebRTC path %s", envelope["payload"].get("path"))
            return
        session_id = envelope.get("sessionId") or self.session_id
        sdp = envelope["payload"].get("sdp")
        if not isinstance(session_id, str) or session_id != self.session_id or not isinstance(sdp, str):
            LOGGER.warning("Mock Robot ignoring invalid pilot-input WebRTC offer")
            return
        if self.pilot_input_webrtc is None:
            self.pilot_input_webrtc = PilotInputWebRtcReceiver(self.receive_pilot_input_snapshot)
        answer_sdp = await self.pilot_input_webrtc.accept_offer(session_id=session_id, sdp=sdp)
        await websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_WEBRTC_ANSWER,
                    {"path": WEBRTC_PATH_PILOT_INPUT, "sdp": answer_sdp},
                    reply_to_message_id=envelope["messageId"],
                    robot_id=self.config.robot_id,
                    session_id=session_id,
                )
            )
        )

    async def handle_webrtc_answer(self, envelope: Mapping[str, Any]) -> None:
        if envelope["payload"].get("path") != WEBRTC_PATH_CAMERA_MEDIA:
            LOGGER.info("Mock Robot ignoring unsupported WebRTC answer path %s", envelope["payload"].get("path"))
            return
        session_id = envelope.get("sessionId") or self.session_id
        sdp = envelope["payload"].get("sdp")
        if not isinstance(session_id, str) or not isinstance(sdp, str):
            LOGGER.warning("Mock Robot ignoring invalid camera-media WebRTC answer")
            return
        if self.camera_media_webrtc is None:
            LOGGER.warning("Mock Robot received camera-media answer without an active publisher")
            return
        await self.camera_media_webrtc.accept_answer(session_id=session_id, sdp=sdp)

    async def _start_camera_media(self, websocket: Any) -> None:
        if self.session_id is None or self.camera is None:
            return
        try:
            if self.camera_media_webrtc is None:
                self.camera_media_webrtc = CameraMediaWebRtcPublisher()
            sdp = await self.camera_media_webrtc.create_offer(
                session_id=self.session_id,
                video_path=self.camera.path,
                loop=self.camera.loop,
            )
        except Exception as exc:
            LOGGER.error("Mock Robot failed to start cameraMedia WebRTC: %s", exc)
            return
        await websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_WEBRTC_OFFER,
                    {"path": WEBRTC_PATH_CAMERA_MEDIA, "sdp": sdp},
                    robot_id=self.config.robot_id,
                    session_id=self.session_id,
                )
            )
        )

    def receive_pilot_input_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        """Receive and log a Pilot Input Snapshot.

        The mock keeps no fake robot pose; stdout logging is the observable
        behavior requested for end-to-end session/control testing.
        """

        payload = dict(snapshot)
        LOGGER.info("pilot_input_snapshot %s", json.dumps(payload, sort_keys=True))

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

    async def _clear_session(self) -> None:
        session_id = self.session_id
        if self.camera is not None:
            self.camera.close()
        if self.pilot_input_webrtc is not None:
            await self.pilot_input_webrtc.close_session(session_id)
        if self.camera_media_webrtc is not None:
            await self.camera_media_webrtc.close_session(session_id)
        self.session_id = None
        self.session_config = None


async def run(config: MockRobotConfig | None = None) -> None:
    await MockRobotDriver(config or MockRobotConfig.from_env()).run_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
