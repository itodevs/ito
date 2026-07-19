"""Environment-backed configuration for the Ito application."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


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
class DataChannelConfig:
    ordered: bool
    max_retransmits: int | None = None

    def to_protocol(self) -> dict[str, int | bool]:
        payload: dict[str, int | bool] = {"ordered": self.ordered}
        if self.max_retransmits is not None:
            payload["maxRetransmits"] = self.max_retransmits
        return payload


@dataclass(frozen=True)
class ItoConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    request_timeout_ms: int = 5000
    robot_backend: str = "local"
    client_dir: Path = Path(__file__).resolve().parents[2] / "client"
    pilot_input_data_channel: DataChannelConfig = DataChannelConfig(
        ordered=False, max_retransmits=0
    )
    splat_batch_data_channel: DataChannelConfig = DataChannelConfig(ordered=True)

    def __post_init__(self) -> None:
        if self.robot_backend not in {"local", "remote"}:
            raise ValueError("robot_backend must be local or remote")

    @classmethod
    def from_env(cls) -> "ItoConfig":
        return cls(
            host=os.getenv("ITO_HOST", cls.host),
            port=_env_int("ITO_PORT", cls.port, minimum=1),
            request_timeout_ms=_env_int(
                "ITO_REQUEST_TIMEOUT_MS", cls.request_timeout_ms, minimum=1
            ),
            robot_backend=os.getenv("ITO_ROBOT_BACKEND", cls.robot_backend),
            client_dir=Path(os.getenv("ITO_CLIENT_DIR", str(cls.client_dir))),
            pilot_input_data_channel=DataChannelConfig(
                ordered=_env_bool("ITO_PILOT_INPUT_ORDERED", False),
                max_retransmits=_env_int(
                    "ITO_PILOT_INPUT_MAX_RETRANSMITS", 0, minimum=0
                ),
            ),
            splat_batch_data_channel=DataChannelConfig(
                ordered=_env_bool("ITO_SPLAT_BATCH_ORDERED", True)
            ),
        )

    def control_config_payload(self) -> dict[str, object]:
        return {
            "pilotInputDataChannel": self.pilot_input_data_channel.to_protocol(),
            "splatBatchDataChannel": self.splat_batch_data_channel.to_protocol(),
        }
