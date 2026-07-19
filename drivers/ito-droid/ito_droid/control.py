"""Ito Droid camera-pan control logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .config import ItoDroidConfig


@dataclass(frozen=True)
class PilotInputSnapshot:
    headset_yaw_radians: float
    received_at_seconds: float


class CameraPanController:
    """Maps pilot yaw snapshots to bounded camera-pan servo commands."""

    def __init__(self, config: ItoDroidConfig) -> None:
        self.config = config
        self.command_degrees = config.servo_neutral_degrees
        self._latest_snapshot: PilotInputSnapshot | None = None
        self._control_lost = False
        self._resumed_at_seconds: float | None = None

    def neutral_angle(self) -> float:
        return self.config.servo_neutral_degrees

    def neutralize(self) -> float:
        self.command_degrees = self.config.servo_neutral_degrees
        self._latest_snapshot = None
        self._control_lost = False
        self._resumed_at_seconds = None
        return self.command_degrees

    def receive_snapshot(self, snapshot: Mapping[str, Any], now_seconds: float) -> PilotInputSnapshot:
        yaw = snapshot.get("headsetYawRad")
        if not isinstance(yaw, (int, float)):
            raise ValueError("Pilot Input Snapshot requires numeric headsetYawRad")
        parsed = PilotInputSnapshot(float(yaw), now_seconds)
        was_lost = self._control_lost
        self._latest_snapshot = parsed
        if was_lost:
            self._control_lost = False
            self._resumed_at_seconds = now_seconds
        return parsed

    def target_for_yaw(self, headset_yaw_radians: float) -> float:
        raw = (
            self.config.servo_neutral_degrees
            + headset_yaw_radians * self.config.yaw_to_servo_degrees_per_radian
        )
        return _clamp(raw, self.config.servo_min_degrees, self.config.servo_max_degrees)

    def tick(self, now_seconds: float, dt_seconds: float) -> float:
        snapshot = self._latest_snapshot
        if snapshot is None:
            return self.command_degrees

        age_ms = (now_seconds - snapshot.received_at_seconds) * 1000
        if age_ms > self.config.pilot_input_timeout_ms:
            self._control_lost = True
            self._resumed_at_seconds = None
            self.command_degrees = self.config.servo_neutral_degrees
            return self.command_degrees

        target = self.target_for_yaw(snapshot.headset_yaw_radians)
        smoothed_target = self.command_degrees + (
            target - self.command_degrees
        ) * self.config.servo_smoothing
        max_delta = self._allowed_velocity(now_seconds) * max(dt_seconds, 0)
        delta = _clamp(smoothed_target - self.command_degrees, -max_delta, max_delta)
        self.command_degrees = _clamp(
            self.command_degrees + delta,
            self.config.servo_min_degrees,
            self.config.servo_max_degrees,
        )
        return self.command_degrees

    def _allowed_velocity(self, now_seconds: float) -> float:
        max_velocity = self.config.servo_max_velocity_degrees_per_second
        if self._resumed_at_seconds is None:
            return max_velocity
        ramp_duration = self.config.resumption_ramp_duration_ms / 1000
        if ramp_duration <= 0:
            return max_velocity
        progress = _clamp((now_seconds - self._resumed_at_seconds) / ramp_duration, 0, 1)
        start = self.config.resumption_initial_velocity_degrees_per_second
        return start + (max_velocity - start) * progress


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
