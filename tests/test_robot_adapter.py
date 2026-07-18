import asyncio

from server.ito.robot import LocalRobotAdapter
from server.processors.base import ReconstructionFrame


def test_local_robot_adapter_moves_sensor_and_control_data_in_process():
    frames = []
    controls = []
    safe_stops = []
    adapter = LocalRobotAdapter(
        control_sink=controls.append,
        safe_stop=lambda: safe_stops.append(True),
    )
    adapter.set_sensor_sink(frames.append)

    adapter.start_control()
    frame = ReconstructionFrame(b"rgb", 1, 1, 1)
    adapter.publish_sensor_frame(frame)
    adapter.receive_pilot_input({"sequence": 1, "headsetYawRad": 0.25})
    adapter.stop_control()

    assert frames == [frame]
    assert controls == [{"sequence": 1, "headsetYawRad": 0.25}]
    assert safe_stops == [True]
    assert adapter.control_active is False


def test_local_robot_adapter_ignores_control_when_paused():
    controls = []
    adapter = LocalRobotAdapter(control_sink=controls.append)

    adapter.receive_pilot_input({"sequence": 1})
    adapter.start_control()
    adapter.stop_control()
    adapter.receive_pilot_input({"sequence": 2})

    assert controls == []


def test_local_robot_adapter_neutralizes_when_pilot_input_times_out():
    async def scenario():
        controls = []
        safe_stops = []
        adapter = LocalRobotAdapter(
            control_sink=controls.append,
            safe_stop=lambda: safe_stops.append(True),
            pilot_input_timeout_ms=10,
        )

        adapter.start_control()
        adapter.receive_pilot_input({"sequence": 1})
        await asyncio.sleep(0.02)

        assert controls == [{"sequence": 1}]
        assert safe_stops == [True]
        assert adapter.input_timed_out is True

    asyncio.run(scenario())


def test_local_robot_adapter_rate_limits_and_keeps_the_newest_input():
    async def scenario():
        controls = []
        adapter = LocalRobotAdapter(
            control_sink=controls.append,
            pilot_input_timeout_ms=1000,
            max_control_rate_hz=20,
        )

        adapter.start_control()
        adapter.receive_pilot_input({"sequence": 1})
        adapter.receive_pilot_input({"sequence": 2})
        adapter.receive_pilot_input({"sequence": 3})
        await asyncio.sleep(0.06)
        adapter.stop_control()

        assert controls == [{"sequence": 1}, {"sequence": 3}]

    asyncio.run(scenario())


def test_local_robot_adapter_emergency_stop_is_latched_until_control_restarts():
    controls = []
    emergency_stops = []
    adapter = LocalRobotAdapter(
        control_sink=controls.append,
        emergency_stop=lambda: emergency_stops.append(True),
    )

    adapter.start_control()
    adapter.emergency_stop()
    adapter.receive_pilot_input({"sequence": 1})

    assert emergency_stops == [True]
    assert controls == []
    assert adapter.control_active is False
