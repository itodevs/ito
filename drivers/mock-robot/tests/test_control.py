from app.control import ControlState

def test_control_sequence_enable_and_watchdog():
    state = ControlState()
    assert state.handle({"type": "control", "sequence": 2, "enabled": True}, now=1.0)
    assert state.enabled
    assert not state.handle({"type": "control", "sequence": 1, "enabled": True}, now=1.1)
    state.check_watchdog(now=1.51)
    assert not state.enabled
    assert state.stops == ["watchdog-timeout"]

def test_disabled_command_stops():
    state = ControlState(enabled=True, last_sequence=1)
    assert state.handle({"type": "control", "sequence": 2, "enabled": False, "reason": "operator-stop"})
    assert state.stops == ["operator-stop"]
