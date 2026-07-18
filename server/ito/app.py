"""The single Ito application: web host, pilot endpoint, and robot control."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
import mimetypes
from typing import Any
from urllib.parse import unquote, urlsplit

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

from .config import ItoConfig
from .protocol import (
    DisplayReason,
    PROTOCOL_VERSION,
    ProtocolError,
    ROLE_PILOT_CLIENT,
    ROLE_REMOTE_ROBOT_DRIVER,
    TYPE_CONNECTION_HELLO,
    TYPE_CONNECTION_HELLO_RESULT,
    TYPE_CONTROL_START,
    TYPE_CONTROL_START_RESULT,
    TYPE_CONTROL_STOP,
    TYPE_CONTROL_STOP_RESULT,
    TYPE_CONTROL_STOPPED,
    TYPE_ROBOT_READY,
    TYPE_DRIVER_CONTROL_START_RESULT,
    TYPE_DRIVER_CONTROL_STOP_RESULT,
    TYPE_WEBRTC_ANSWER,
    TYPE_WEBRTC_OFFER,
    WEBRTC_PATH_CAMERA_MEDIA,
    WEBRTC_PATH_PILOT_INPUT,
    WEBRTC_PATH_SPLAT_BATCHES,
    make_envelope,
    pack_envelope,
    result_error,
    result_ok,
    unpack_envelope,
)
from .reconstruction import ReconstructionRuntime
from .media import AiortcCameraTrackReceiver
from .robot import LocalRobotAdapter, RemoteRobotAdapter
from .webrtc import MissingWebRtcStack, ServerLivePathAcceptor, SplatBatchChannel
from server.processors.null import NullReconstructionProcessor
from server.processors.base import ReconstructionProcessor

LOGGER = logging.getLogger(__name__)


@dataclass(eq=False)
class ConnectionState:
    websocket: ServerConnection
    role: str | None = None


class ItoApplication:
    def __init__(
        self,
        config: ItoConfig | None = None,
        *,
        adapter: LocalRobotAdapter | RemoteRobotAdapter | None = None,
        processor_factory: Callable[[], ReconstructionProcessor] | None = None,
    ) -> None:
        self.config = config or ItoConfig.from_env()
        if adapter is None:
            adapter = (
                RemoteRobotAdapter(request_timeout_ms=self.config.request_timeout_ms)
                if self.config.robot_backend == "remote"
                else LocalRobotAdapter(ready=False)
            )
        self.adapter = adapter
        self.processor_factory = processor_factory or NullReconstructionProcessor
        self.pilot: ConnectionState | None = None
        self.control_active = False
        self.splat_channels = SplatBatchChannel()
        self.live_paths: ServerLivePathAcceptor = MissingWebRtcStack()
        self.reconstruction_runtime: ReconstructionRuntime | None = None
        if isinstance(self.adapter, LocalRobotAdapter):
            self.adapter.set_sensor_sink(self._process_sensor_frame)
        self._install_default_live_paths()

    def _install_default_live_paths(self) -> None:
        try:
            from .webrtc import AiortcServerLivePaths

            self.live_paths = AiortcServerLivePaths(
                on_camera_track=self._accept_camera_track,
                on_pilot_input=(
                    self.adapter.receive_pilot_input
                    if isinstance(self.adapter, LocalRobotAdapter)
                    else None
                ),
                splat_channels=self.splat_channels,
            )
        except RuntimeError:
            self.live_paths = MissingWebRtcStack()

    async def serve_forever(self) -> None:
        LOGGER.info(
            "Starting Ito application on http://%s:%s with %s robot adapter",
            self.config.host,
            self.config.port,
            self.config.robot_backend,
        )
        async with serve(
            self._handle_connection,
            self.config.host,
            self.config.port,
            process_request=self.process_http_request,
        ):
            await asyncio.Future()

    async def process_http_request(self, _connection: object, request: object) -> Response | None:
        request_path = urlsplit(request.path).path
        if request_path == "/ws":
            return None
        relative_path = unquote(request_path).lstrip("/") or "index.html"
        client_dir = self.config.client_dir.resolve()
        candidate = (client_dir / relative_path).resolve()
        if client_dir not in candidate.parents and candidate != client_dir:
            return self._http_response(404, b"Not found", "text/plain; charset=utf-8")
        if candidate.is_dir():
            candidate = candidate / "index.html"
        try:
            body = candidate.read_bytes()
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            return self._http_response(404, b"Not found", "text/plain; charset=utf-8")
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        return self._http_response(200, body, content_type)

    @staticmethod
    def _http_response(status: int, body: bytes, content_type: str) -> Response:
        reason = "OK" if status == 200 else "Not Found"
        return Response(
            status,
            reason,
            Headers(
                {
                    "Content-Type": content_type,
                    "Content-Length": str(len(body)),
                    "Cache-Control": "no-cache",
                }
            ),
            body,
        )

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        state = ConnectionState(websocket)
        try:
            async for frame in websocket:
                await self._handle_frame(state, frame)
        except ConnectionClosed:
            pass
        finally:
            await self._disconnect(state)

    async def _disconnect(self, state: ConnectionState) -> None:
        if self.pilot is state:
            await self._stop_control(
                {"code": "control.stopped.pilot_disconnected"}, notify=False
            )
            self.pilot = None
        if (
            state.role == ROLE_REMOTE_ROBOT_DRIVER
            and isinstance(self.adapter, RemoteRobotAdapter)
            and self.adapter.connection is state.websocket
        ):
            self.adapter.detach(state.websocket)
            await self._notify_robot_ready(False)
            await self._stop_control(
                {"code": "control.stopped.robot_driver_disconnected"}
            )

    async def _handle_frame(self, state: ConnectionState, frame: bytes | str) -> None:
        if not isinstance(frame, bytes):
            await self._send_error(
                state, TYPE_CONNECTION_HELLO_RESULT, None, "protocol.invalid_frame"
            )
            return
        try:
            envelope = unpack_envelope(frame)
        except ProtocolError:
            await self._send_error(
                state, TYPE_CONNECTION_HELLO_RESULT, None, "protocol.invalid_message"
            )
            return
        if state.role is None and envelope["type"] != TYPE_CONNECTION_HELLO:
            await self._send_error(
                state,
                TYPE_CONNECTION_HELLO_RESULT,
                envelope["messageId"],
                "connection.hello_required",
            )
            return

        message_type = envelope["type"]
        if message_type == TYPE_CONNECTION_HELLO:
            await self._handle_hello(state, envelope)
        elif message_type == TYPE_CONTROL_START:
            await self._handle_control_start(state, envelope)
        elif message_type == TYPE_CONTROL_STOP:
            await self._handle_control_stop(state, envelope)
        elif (
            message_type in {
            TYPE_DRIVER_CONTROL_START_RESULT,
            TYPE_DRIVER_CONTROL_STOP_RESULT,
            TYPE_WEBRTC_ANSWER,
            }
            and state.role == ROLE_REMOTE_ROBOT_DRIVER
            and isinstance(self.adapter, RemoteRobotAdapter)
            and self.adapter.connection is state.websocket
        ):
            self.adapter.handle_response(envelope)
        elif message_type == TYPE_WEBRTC_OFFER:
            await self._handle_webrtc_offer(state, envelope)
        else:
            await self._send_error(
                state,
                TYPE_CONNECTION_HELLO_RESULT,
                envelope["messageId"],
                "protocol.unsupported_message",
            )

    async def _handle_hello(self, state: ConnectionState, envelope: dict[str, Any]) -> None:
        role = envelope["payload"].get("role")
        if role == ROLE_REMOTE_ROBOT_DRIVER:
            await self._handle_remote_driver_hello(state, envelope)
            return
        if role != ROLE_PILOT_CLIENT:
            await self._send_error(
                state,
                TYPE_CONNECTION_HELLO_RESULT,
                envelope["messageId"],
                "connection.invalid_role",
            )
            return
        if self.pilot is not None and self.pilot is not state:
            await self._send_error(
                state,
                TYPE_CONNECTION_HELLO_RESULT,
                envelope["messageId"],
                "connection.pilot_already_connected",
            )
            return
        state.role = ROLE_PILOT_CLIENT
        self.pilot = state
        await self._send_result(
            state,
            TYPE_CONNECTION_HELLO_RESULT,
            envelope["messageId"],
            result_ok(
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "robotReady": self.adapter.ready,
                    "controlActive": self.control_active,
                    "controlConfig": self.config.control_config_payload(),
                }
            ),
        )

    async def _handle_remote_driver_hello(
        self, state: ConnectionState, envelope: dict[str, Any]
    ) -> None:
        if not isinstance(self.adapter, RemoteRobotAdapter):
            await self._send_error(
                state,
                TYPE_CONNECTION_HELLO_RESULT,
                envelope["messageId"],
                "connection.remote_driver_not_configured",
            )
            return
        if self.adapter.connection not in {None, state.websocket}:
            await self._send_error(
                state,
                TYPE_CONNECTION_HELLO_RESULT,
                envelope["messageId"],
                "connection.remote_driver_already_connected",
            )
            return
        ready = envelope["payload"].get("ready")
        if not isinstance(ready, bool):
            await self._send_error(
                state,
                TYPE_CONNECTION_HELLO_RESULT,
                envelope["messageId"],
                "connection.remote_driver_ready_required",
            )
            return
        state.role = ROLE_REMOTE_ROBOT_DRIVER
        self.adapter.attach(state.websocket, ready=ready)
        await self._send_result(
            state,
            TYPE_CONNECTION_HELLO_RESULT,
            envelope["messageId"],
            result_ok({"protocolVersion": PROTOCOL_VERSION}),
        )
        await self._notify_robot_ready(ready)

    async def _handle_control_start(
        self, state: ConnectionState, envelope: dict[str, Any]
    ) -> None:
        if state is not self.pilot:
            await self._send_error(
                state,
                TYPE_CONTROL_START_RESULT,
                envelope["messageId"],
                "control.pilot_required",
            )
            return
        if not self.adapter.ready:
            await self._send_error(
                state,
                TYPE_CONTROL_START_RESULT,
                envelope["messageId"],
                "robot.not_ready",
            )
            return
        if not self.control_active:
            self._start_reconstruction()
            try:
                await _maybe_await(self.adapter.start_control())
            except Exception as exc:
                LOGGER.warning("Robot adapter refused control start: %s", exc)
                try:
                    await _maybe_await(self.adapter.stop_control())
                except Exception:
                    LOGGER.exception("Robot adapter cleanup failed after start refusal")
                runtime = self.reconstruction_runtime
                self.reconstruction_runtime = None
                if runtime is not None:
                    runtime.close()
                await self._send_result(
                    state,
                    TYPE_CONTROL_START_RESULT,
                    envelope["messageId"],
                    result_error(
                        DisplayReason(code="control.start_failed", text=str(exc))
                    ),
                )
                return
            self.control_active = True
        await self._send_result(
            state,
            TYPE_CONTROL_START_RESULT,
            envelope["messageId"],
            result_ok({"controlConfig": self.config.control_config_payload()}),
        )

    async def _handle_control_stop(
        self, state: ConnectionState, envelope: dict[str, Any]
    ) -> None:
        if state is not self.pilot:
            await self._send_error(
                state,
                TYPE_CONTROL_STOP_RESULT,
                envelope["messageId"],
                "control.pilot_required",
            )
            return
        reason = envelope["payload"].get("reason")
        if not isinstance(reason, dict):
            reason = {"code": "control.stopped.pilot_requested"}
        await self._send_result(
            state,
            TYPE_CONTROL_STOP_RESULT,
            envelope["messageId"],
            result_ok(),
        )
        await self._stop_control(reason)

    def _start_reconstruction(self) -> None:
        if self.reconstruction_runtime is not None:
            return
        runtime = ReconstructionRuntime(
            self.processor_factory(),
            send_splat_batch=self.splat_channels.send,
            fail_control=lambda reason: asyncio.create_task(
                self._stop_control(reason)
            ),
        )
        runtime.start()
        self.reconstruction_runtime = runtime

    def _process_sensor_frame(self, frame: object) -> None:
        if self.control_active and self.reconstruction_runtime is not None:
            self.reconstruction_runtime.process_frame(frame)

    def _accept_camera_track(self, track: object) -> None:
        if getattr(track, "kind", None) != "video":
            return
        receiver = AiortcCameraTrackReceiver(self._process_sensor_frame)
        asyncio.create_task(receiver.consume(track))

    async def _handle_webrtc_offer(
        self, state: ConnectionState, envelope: dict[str, Any]
    ) -> None:
        if not self.control_active:
            return
        path = envelope["payload"].get("path")
        sdp = envelope["payload"].get("sdp")
        if not isinstance(sdp, str):
            return
        try:
            if (
                path == WEBRTC_PATH_PILOT_INPUT
                and state is self.pilot
                and isinstance(self.adapter, RemoteRobotAdapter)
            ):
                answer_sdp = await self.adapter.accept_pilot_input_offer(sdp)
            elif path in {WEBRTC_PATH_PILOT_INPUT, WEBRTC_PATH_SPLAT_BATCHES} and state is self.pilot:
                answer_sdp = await self.live_paths.accept_offer(
                    path=path, sdp=sdp
                )
            elif (
                path == WEBRTC_PATH_CAMERA_MEDIA
                and state.role == ROLE_REMOTE_ROBOT_DRIVER
                and isinstance(self.adapter, RemoteRobotAdapter)
                and self.adapter.connection is state.websocket
            ):
                answer_sdp = await self.live_paths.accept_offer(
                    path=path, sdp=sdp
                )
            else:
                return
        except Exception as exc:
            LOGGER.exception("WebRTC negotiation failed for %s", path)
            await self._stop_control(
                {"code": "control.stopped.transport_failed", "text": str(exc)}
            )
            return
        await state.websocket.send(
            pack_envelope(
                make_envelope(
                    TYPE_WEBRTC_ANSWER,
                    {"path": path, "sdp": answer_sdp},
                    reply_to_message_id=envelope["messageId"],
                )
            )
        )

    async def _stop_control(
        self, reason: dict[str, str], *, notify: bool = True
    ) -> None:
        was_active = self.control_active
        self.control_active = False
        if was_active:
            await _maybe_await(self.adapter.stop_control())
        runtime = self.reconstruction_runtime
        self.reconstruction_runtime = None
        if runtime is not None:
            runtime.close()
        close_control = getattr(self.live_paths, "close_control", None)
        if close_control is not None:
            await close_control()
        if notify and self.pilot is not None:
            await self.pilot.websocket.send(
                pack_envelope(
                    make_envelope(TYPE_CONTROL_STOPPED, {"reason": reason})
                )
            )

    async def _notify_robot_ready(self, ready: bool) -> None:
        if self.pilot is None:
            return
        await self.pilot.websocket.send(
            pack_envelope(make_envelope(TYPE_ROBOT_READY, {"ready": ready}))
        )

    async def _send_error(
        self,
        state: ConnectionState,
        message_type: str,
        reply_to: str | None,
        code: str,
    ) -> None:
        await self._send_result(
            state,
            message_type,
            reply_to,
            result_error(DisplayReason(code=code)),
        )

    async def _send_result(
        self,
        state: ConnectionState,
        message_type: str,
        reply_to: str | None,
        payload: dict[str, Any],
    ) -> None:
        await state.websocket.send(
            pack_envelope(
                make_envelope(
                    message_type, payload, reply_to_message_id=reply_to
                )
            )
        )


async def _maybe_await(result: object) -> object:
    if asyncio.iscoroutine(result):
        return await result
    return result


async def run(config: ItoConfig | None = None) -> None:
    await ItoApplication(config).serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
