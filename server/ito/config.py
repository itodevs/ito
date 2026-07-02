"""Environment-backed Ito Server configuration."""

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
class DataChannelConfig:
    """WebRTC data channel reliability/ordering profile exposed in sessions."""

    ordered: bool
    max_retransmits: int | None = None
    max_packet_lifetime_ms: int | None = None

    def to_protocol(self) -> dict[str, int | bool]:
        payload: dict[str, int | bool] = {"ordered": self.ordered}
        if self.max_retransmits is not None:
            payload["maxRetransmits"] = self.max_retransmits
        if self.max_packet_lifetime_ms is not None:
            payload["maxPacketLifeTime"] = self.max_packet_lifetime_ms
        return payload


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    request_timeout_ms: int = 5000
    driver_status_watchdog_ms: int = 2000
    session_cleanup_timeout_ms: int = 30000
    pilot_input_data_channel: DataChannelConfig = DataChannelConfig(
        ordered=False, max_retransmits=0
    )
    splat_batch_data_channel: DataChannelConfig = DataChannelConfig(ordered=True)

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            host=os.getenv("ITO_SERVER_HOST", cls.host),
            port=_env_int("ITO_SERVER_PORT", cls.port, minimum=1),
            request_timeout_ms=_env_int(
                "ITO_REQUEST_TIMEOUT_MS", cls.request_timeout_ms, minimum=1
            ),
            driver_status_watchdog_ms=_env_int(
                "ITO_DRIVER_STATUS_WATCHDOG_MS",
                cls.driver_status_watchdog_ms,
                minimum=1,
            ),
            session_cleanup_timeout_ms=_env_int(
                "ITO_SESSION_CLEANUP_TIMEOUT_MS",
                cls.session_cleanup_timeout_ms,
                minimum=1,
            ),
            pilot_input_data_channel=_data_channel_config_from_env(
                ordered_name="ITO_PILOT_INPUT_ORDERED",
                ordered_default=False,
                max_retransmits_name="ITO_PILOT_INPUT_MAX_RETRANSMITS",
                max_retransmits_default=0,
                max_packet_lifetime_name="ITO_PILOT_INPUT_MAX_PACKET_LIFETIME_MS",
            ),
            splat_batch_data_channel=_data_channel_config_from_env(
                ordered_name="ITO_SPLAT_BATCH_ORDERED",
                ordered_default=True,
                max_retransmits_name="ITO_SPLAT_BATCH_MAX_RETRANSMITS",
                max_retransmits_default=None,
                max_packet_lifetime_name="ITO_SPLAT_BATCH_MAX_PACKET_LIFETIME_MS",
            ),
        )

    def session_config_payload(self) -> dict[str, object]:
        return {
            "pilotInputDataChannel": self.pilot_input_data_channel.to_protocol(),
            "splatBatchDataChannel": self.splat_batch_data_channel.to_protocol(),
        }


def _optional_int(name: str, default: int | None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return _env_int(name, 0, minimum=0)


def _env_is_set(name: str) -> bool:
    raw = os.getenv(name)
    return raw is not None and raw != ""


def _data_channel_config_from_env(
    *,
    ordered_name: str,
    ordered_default: bool,
    max_retransmits_name: str,
    max_retransmits_default: int | None,
    max_packet_lifetime_name: str,
) -> DataChannelConfig:
    has_max_retransmits = _env_is_set(max_retransmits_name)
    has_max_packet_lifetime = _env_is_set(max_packet_lifetime_name)
    if has_max_retransmits and has_max_packet_lifetime:
        raise ValueError(
            f"{max_retransmits_name} and {max_packet_lifetime_name} are mutually exclusive"
        )

    max_packet_lifetime_ms = _optional_int(max_packet_lifetime_name, None)
    max_retransmits = _optional_int(
        max_retransmits_name,
        None if has_max_packet_lifetime else max_retransmits_default,
    )
    return DataChannelConfig(
        ordered=_env_bool(ordered_name, ordered_default),
        max_retransmits=max_retransmits,
        max_packet_lifetime_ms=max_packet_lifetime_ms,
    )
