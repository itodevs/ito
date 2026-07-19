"""Narrow robot integration seam for the Ito application."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import asyncio
import time
from typing import Any

from .protocol import (
    DisplayReason,
    TYPE_DRIVER_CONTROL_START,
    TYPE_DRIVER_CONTROL_START_RESULT,
    TYPE_DRIVER_CONTROL_STOP,
    TYPE_DRIVER_CONTROL_STOP_RESULT,
    TYPE_WEBRTC_ANSWER,
    TYPE_WEBRTC_OFFER,
    WEBRTC_PATH_PILOT_INPUT,
    make_envelope,
    pack_envelope,
)
from server.processors.base import ReconstructionFrame


class LocalRobotAdapter:
    """In-process robot integration used by the normal onboard deployment."""

    def __init__(
        self,
        *,
        control_sink: Callable[[Mapping[str, Any]], None] | None = None,
        safe_stop: Callable[[], None] | None = None,
        emergency_stop: Callable[[], None] | None = None,
        safe_resume: Callable[[], None] | None = None,
        ready: bool = True,
        pilot_input_timeout_ms: int = 500,
        max_control_rate_hz: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if pilot_input_timeout_ms <= 0:
            raise ValueError("pilot_input_timeout_ms must be positive")
        if max_control_rate_hz <= 0:
            raise ValueError("max_control_rate_hz must be positive")
        self.control_active = False
        self.ready = ready
        self.input_timed_out = False
        self._control_sink = control_sink
        self._safe_stop = safe_stop
        self._emergency_stop = emergency_stop or safe_stop
        self._safe_resume = safe_resume
        self._sensor_sink: Callable[[ReconstructionFrame], None] | None = None
        self._pilot_input_timeout_seconds = pilot_input_timeout_ms / 1000
        self._control_interval_seconds = 1 / max_control_rate_hz
        self._clock = clock
        self._latest_snapshot: Mapping[str, Any] | None = None
        self._last_forwarded_at: float | None = None
        self._input_timeout_handle: asyncio.TimerHandle | None = None
        self._rate_limit_handle: asyncio.TimerHandle | None = None

    def set_sensor_sink(self, sink: Callable[[ReconstructionFrame], None]) -> None:
        self._sensor_sink = sink

    def publish_sensor_frame(self, frame: ReconstructionFrame) -> None:
        if self._sensor_sink is not None:
            self._sensor_sink(frame)

    def start_control(self) -> None:
        self._cancel_timers()
        self.control_active = True
        self.input_timed_out = False
        self._latest_snapshot = None
        self._last_forwarded_at = None

    def receive_pilot_input(self, snapshot: Mapping[str, Any]) -> None:
        if not self.control_active:
            return
        self._latest_snapshot = dict(snapshot)
        self._arm_input_timeout()
        now = self._clock()
        if (
            self._last_forwarded_at is None
            or now - self._last_forwarded_at >= self._control_interval_seconds
        ):
            self._flush_latest_input()
            return
        if self._rate_limit_handle is None:
            delay = self._control_interval_seconds - (now - self._last_forwarded_at)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._flush_latest_input()
                return
            self._rate_limit_handle = loop.call_later(
                max(delay, 0), self._flush_latest_input
            )

    def stop_control(self) -> None:
        was_active = self.control_active
        self.control_active = False
        self._cancel_timers()
        self._latest_snapshot = None
        if was_active and self._safe_stop is not None:
            self._safe_stop()

    def emergency_stop(self) -> None:
        """Latch a robot-local stop until an explicit control start."""

        was_active = self.control_active
        self.control_active = False
        self.input_timed_out = True
        self._cancel_timers()
        self._latest_snapshot = None
        if was_active and self._emergency_stop is not None:
            self._emergency_stop()

    def _arm_input_timeout(self) -> None:
        if self._input_timeout_handle is not None:
            self._input_timeout_handle.cancel()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._input_timeout_handle = loop.call_later(
            self._pilot_input_timeout_seconds, self._handle_input_timeout
        )

    def _handle_input_timeout(self) -> None:
        self._input_timeout_handle = None
        if not self.control_active or self.input_timed_out:
            return
        self.input_timed_out = True
        self._latest_snapshot = None
        if self._rate_limit_handle is not None:
            self._rate_limit_handle.cancel()
            self._rate_limit_handle = None
        if self._safe_stop is not None:
            self._safe_stop()

    def _flush_latest_input(self) -> None:
        self._rate_limit_handle = None
        snapshot = self._latest_snapshot
        self._latest_snapshot = None
        if not self.control_active or snapshot is None:
            return
        if self.input_timed_out:
            if self._safe_resume is not None:
                self._safe_resume()
            self.input_timed_out = False
        self._last_forwarded_at = self._clock()
        if self._control_sink is not None:
            self._control_sink(snapshot)

    def _cancel_timers(self) -> None:
        for handle in (self._input_timeout_handle, self._rate_limit_handle):
            if handle is not None:
                handle.cancel()
        self._input_timeout_handle = None
        self._rate_limit_handle = None


class RemoteRobotAdapter:
    """Proxy for the single lightweight driver used by external Ito deployments."""

    def __init__(self, *, request_timeout_ms: int = 5000) -> None:
        self.request_timeout_ms = request_timeout_ms
        self.connection: object | None = None
        self.ready = False
        self.control_active = False
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def attach(self, connection: object, *, ready: bool) -> None:
        self.connection = connection
        self.ready = ready

    def detach(self, connection: object) -> None:
        if self.connection is not connection:
            return
        self.connection = None
        self.ready = False
        self.control_active = False
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RuntimeError("remote robot driver disconnected"))
        self._pending.clear()

    async def start_control(self) -> None:
        result = await self._request(
            TYPE_DRIVER_CONTROL_START,
            {},
            TYPE_DRIVER_CONTROL_START_RESULT,
        )
        self._require_ok(result)
        self.control_active = True

    async def stop_control(self) -> None:
        if self.connection is not None and self.control_active:
            result = await self._request(
                TYPE_DRIVER_CONTROL_STOP,
                {"reason": {"code": "control.stopped.ito_requested"}},
                TYPE_DRIVER_CONTROL_STOP_RESULT,
            )
            self._require_ok(result)
        self.control_active = False

    async def accept_pilot_input_offer(self, sdp: str) -> str:
        result = await self._request(
            TYPE_WEBRTC_OFFER,
            {"path": WEBRTC_PATH_PILOT_INPUT, "sdp": sdp},
            TYPE_WEBRTC_ANSWER,
        )
        answer = result.get("payload", {}).get("sdp")
        if not isinstance(answer, str):
            raise RuntimeError("remote robot driver returned an invalid WebRTC answer")
        return answer

    def handle_response(self, envelope: Mapping[str, Any]) -> bool:
        reply_to = envelope.get("replyToMessageId")
        if not isinstance(reply_to, str):
            return False
        future = self._pending.pop(reply_to, None)
        if future is None or future.done():
            return False
        future.set_result(dict(envelope))
        return True

    async def _request(
        self, message_type: str, payload: Mapping[str, Any], expected_type: str
    ) -> dict[str, Any]:
        if self.connection is None:
            raise RuntimeError("remote robot driver isn't connected")
        request = make_envelope(message_type, payload)
        future = asyncio.get_running_loop().create_future()
        self._pending[request["messageId"]] = future
        try:
            await self.connection.send(pack_envelope(request))
            response = await asyncio.wait_for(
                future, timeout=self.request_timeout_ms / 1000
            )
        finally:
            self._pending.pop(request["messageId"], None)
        if response.get("type") != expected_type:
            raise RuntimeError("remote robot driver returned an unexpected response")
        return response

    @staticmethod
    def _require_ok(envelope: Mapping[str, Any]) -> None:
        payload = envelope.get("payload", {})
        if payload.get("ok"):
            return
        reason = payload.get("reason", {})
        text = reason.get("text") or reason.get("code") or "remote robot request failed"
        raise RuntimeError(text)
