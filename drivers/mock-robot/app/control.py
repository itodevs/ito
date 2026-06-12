import json
import logging
from dataclasses import dataclass, field
from time import monotonic

log = logging.getLogger("ito.recorded_driver")
WATCHDOG_SECONDS = 0.5

@dataclass
class ControlState:
    last_sequence: int = -1
    enabled: bool = False
    last_enabled_at: float = 0.0
    status: object | None = None
    stops: list[str] = field(default_factory=list)

    def send_status(self, payload: dict):
        if self.status and getattr(self.status, "readyState", "closed") == "open":
            self.status.send(json.dumps(payload))

    def safe_stop(self, reason: str):
        was_enabled = self.enabled
        self.enabled = False
        self.stops.append(reason)
        log.warning("safe_stop reason=%s was_enabled=%s", reason, was_enabled)
        self.send_status({"type": "stop-ack", "reason": reason})

    def handle(self, message: dict, now: float | None = None) -> bool:
        if message.get("type") != "control":
            return False
        sequence = message.get("sequence")
        if not isinstance(sequence, int) or sequence <= self.last_sequence:
            return False
        self.last_sequence = sequence
        if not message.get("enabled", False):
            self.safe_stop(message.get("reason", "disabled-command"))
            return True
        self.enabled = True
        self.last_enabled_at = monotonic() if now is None else now
        log.info("accepted_control sequence=%s head=%s", sequence, message.get("head"))
        return True

    def check_watchdog(self, now: float | None = None):
        now = monotonic() if now is None else now
        if self.enabled and now - self.last_enabled_at > WATCHDOG_SECONDS:
            self.safe_stop("watchdog-timeout")
