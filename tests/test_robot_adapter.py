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
