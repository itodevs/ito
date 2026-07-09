"""Environment-backed Mock Robot configuration."""

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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class MockRobotConfig:
    server_url: str = "ws://localhost:8765"
    robot_id: str = "mock-robot-1"
    name: str = "Mock Robot"
    status_interval_ms: int = 1000
    reconnect_initial_delay_ms: int = 250
    reconnect_max_delay_ms: int = 5000
    camera_video_path: str | None = None
    camera_chunk_size: int = 64 * 1024
    camera_loop: bool = True

    @classmethod
    def from_env(cls) -> "MockRobotConfig":
        return cls(
            server_url=os.getenv("ITO_SERVER_URL", cls.server_url),
            robot_id=os.getenv("ITO_MOCK_ROBOT_ID", cls.robot_id),
            name=os.getenv("ITO_MOCK_ROBOT_NAME", cls.name),
            status_interval_ms=_env_int(
                "ITO_MOCK_ROBOT_STATUS_INTERVAL_MS",
                cls.status_interval_ms,
                minimum=1,
            ),
            reconnect_initial_delay_ms=_env_int(
                "ITO_MOCK_ROBOT_RECONNECT_INITIAL_DELAY_MS",
                cls.reconnect_initial_delay_ms,
                minimum=1,
            ),
            reconnect_max_delay_ms=_env_int(
                "ITO_MOCK_ROBOT_RECONNECT_MAX_DELAY_MS",
                cls.reconnect_max_delay_ms,
                minimum=1,
            ),
            camera_video_path=os.getenv("ITO_MOCK_ROBOT_CAMERA_VIDEO"),
            camera_chunk_size=_env_int(
                "ITO_MOCK_ROBOT_CAMERA_CHUNK_SIZE",
                cls.camera_chunk_size,
                minimum=1,
            ),
            camera_loop=_env_bool("ITO_MOCK_ROBOT_CAMERA_LOOP", cls.camera_loop),
        )

