"""Environment-backed Ito Droid driver configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class ItoDroidConfig:
    server_url: str = "ws://localhost:8765"
    robot_id: str = "ito-droid-1"
    name: str = "Ito Droid"
    status_interval_ms: int = 1000
    reconnect_initial_delay_ms: int = 250
    reconnect_max_delay_ms: int = 5000
    ros_camera_topic: str = "/image_raw"
    ros_servo_command_topic: str = "/ito_droid/camera_pan/command"
    ros_node_name: str = "ito_droid_driver"
    pilot_input_timeout_ms: int = 2000
    control_tick_hz: float = 60.0
    servo_neutral_degrees: float = 90.0
    servo_min_degrees: float = 15.0
    servo_max_degrees: float = 165.0
    yaw_to_servo_degrees_per_radian: float = 57.29577951308232
    servo_smoothing: float = 0.35
    servo_max_velocity_degrees_per_second: float = 180.0
    resumption_initial_velocity_degrees_per_second: float = 20.0
    resumption_ramp_duration_ms: int = 1500

    @classmethod
    def from_env(cls) -> "ItoDroidConfig":
        return cls(
            server_url=os.getenv("ITO_SERVER_URL", cls.server_url),
            robot_id=os.getenv("ITO_DROID_ROBOT_ID", cls.robot_id),
            name=os.getenv("ITO_DROID_NAME", cls.name),
            status_interval_ms=_env_int(
                "ITO_DROID_STATUS_INTERVAL_MS",
                cls.status_interval_ms,
                minimum=1,
            ),
            reconnect_initial_delay_ms=_env_int(
                "ITO_DROID_RECONNECT_INITIAL_DELAY_MS",
                cls.reconnect_initial_delay_ms,
                minimum=1,
            ),
            reconnect_max_delay_ms=_env_int(
                "ITO_DROID_RECONNECT_MAX_DELAY_MS",
                cls.reconnect_max_delay_ms,
                minimum=1,
            ),
            ros_camera_topic=os.getenv("ITO_DROID_ROS_CAMERA_TOPIC", cls.ros_camera_topic),
            ros_servo_command_topic=os.getenv(
                "ITO_DROID_ROS_SERVO_COMMAND_TOPIC",
                cls.ros_servo_command_topic,
            ),
            ros_node_name=os.getenv("ITO_DROID_ROS_NODE_NAME", cls.ros_node_name),
            pilot_input_timeout_ms=_env_int(
                "ITO_DROID_PILOT_INPUT_TIMEOUT_MS",
                cls.pilot_input_timeout_ms,
                minimum=1,
            ),
            control_tick_hz=_env_float("ITO_DROID_CONTROL_TICK_HZ", cls.control_tick_hz, minimum=1),
            servo_neutral_degrees=_env_float(
                "ITO_DROID_SERVO_NEUTRAL_DEGREES",
                cls.servo_neutral_degrees,
            ),
            servo_min_degrees=_env_float("ITO_DROID_SERVO_MIN_DEGREES", cls.servo_min_degrees),
            servo_max_degrees=_env_float("ITO_DROID_SERVO_MAX_DEGREES", cls.servo_max_degrees),
            yaw_to_servo_degrees_per_radian=_env_float(
                "ITO_DROID_YAW_TO_SERVO_DEGREES_PER_RADIAN",
                cls.yaw_to_servo_degrees_per_radian,
            ),
            servo_smoothing=_env_float(
                "ITO_DROID_SERVO_SMOOTHING",
                cls.servo_smoothing,
                minimum=0.0,
            ),
            servo_max_velocity_degrees_per_second=_env_float(
                "ITO_DROID_SERVO_MAX_VELOCITY_DEGREES_PER_SECOND",
                cls.servo_max_velocity_degrees_per_second,
                minimum=1.0,
            ),
            resumption_initial_velocity_degrees_per_second=_env_float(
                "ITO_DROID_RESUMPTION_INITIAL_VELOCITY_DEGREES_PER_SECOND",
                cls.resumption_initial_velocity_degrees_per_second,
                minimum=0.0,
            ),
            resumption_ramp_duration_ms=_env_int(
                "ITO_DROID_RESUMPTION_RAMP_DURATION_MS",
                cls.resumption_ramp_duration_ms,
                minimum=0,
            ),
        ).validated()

    def validated(self) -> "ItoDroidConfig":
        if self.servo_min_degrees > self.servo_neutral_degrees:
            raise ValueError("ITO_DROID_SERVO_MIN_DEGREES must be <= neutral")
        if self.servo_neutral_degrees > self.servo_max_degrees:
            raise ValueError("ITO_DROID_SERVO_NEUTRAL_DEGREES must be <= max")
        if self.servo_smoothing > 1:
            raise ValueError("ITO_DROID_SERVO_SMOOTHING must be <= 1")
        if (
            self.resumption_initial_velocity_degrees_per_second
            > self.servo_max_velocity_degrees_per_second
        ):
            raise ValueError("ITO_DROID_RESUMPTION_INITIAL_VELOCITY_DEGREES_PER_SECOND must be <= max velocity")
        return self

