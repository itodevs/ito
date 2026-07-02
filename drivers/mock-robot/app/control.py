"""Latest-value control handling and final watchdog safety for the recorded driver."""

import json
import logging
from dataclasses import dataclass
from time import monotonic

log = logging.getLogger("ito.recorded_driver")
WATCHDOG_SECONDS = 0.5


@dataclass
class ControlState:
    """Track the newest valid control command for one client peer."""

    last_sequence: int = -1
    enabled: bool = False
    last_enabled_at: float = 0.0
    status: object | None = None

    def send_status(self, payload: dict) -> None:
        """Send a reliable status message when the client channel is ready."""
        if self.status and getattr(self.status, "readyState", "closed") == "open":
            self.status.send(json.dumps(payload))

    def safe_stop(self, reason: str) -> None:
        """Disable active commands, log the safety event, and acknowledge it."""
        was_enabled = self.enabled
        self.enabled = False
        log.warning("safe_stop reason=%s was_enabled=%s", reason, was_enabled)
        self.send_status({"type": "stop-ack", "reason": reason})

    def handle(self, message: dict, now: float | None = None) -> bool:
        """Accept only newer control messages and require explicit enable."""
        if message.get("type") != "control":
            return False

        sequence = message.get("sequence")
        if not isinstance(sequence, int) or sequence <= self.last_sequence:
            return False
        self.last_sequence = sequence

        if not message.get("enabled", False):
            # Acknowledge explicit stops and active-to-disabled transitions, not every idle pose.
            reason = message.get("reason")
            if self.enabled or reason:
                self.safe_stop(reason or "disabled-command")
            return True

        self.enabled = True
        self.last_enabled_at = monotonic() if now is None else now
        log.info("accepted_control sequence=%s head=%s", sequence, message.get("head"))
        return True

    def check_watchdog(self, now: float | None = None) -> None:
        """Stop active control when fresh enabled updates disappear for 500 ms."""
        now = monotonic() if now is None else now
        if self.enabled and now - self.last_enabled_at > WATCHDOG_SECONDS:
            self.safe_stop("watchdog-timeout")
