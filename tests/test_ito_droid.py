import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers" / "ito-droid"))

from ito_droid.config import ItoDroidConfig
from ito_droid.control import CameraPanController
from ito_droid.driver import ItoDroidDriver
from ito_droid.media import CameraMediaPublisher
from ito_droid.ros_io import CameraFrame
from ito_droid.webrtc import decode_pilot_input_snapshot
from server.ito.protocol import (
    TYPE_DRIVER_CONTROL_START,
    TYPE_DRIVER_CONTROL_START_RESULT,
    TYPE_DRIVER_CONTROL_STOP,
    TYPE_DRIVER_CONTROL_STOP_RESULT,
    make_envelope,
    unpack_envelope,
)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class RecordingServo:
    def __init__(self):
        self.angles = []

    def publish_angle(self, angle):
        self.angles.append(angle)


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(unpack_envelope(frame))


def test_yaw_mapping_clamps_to_robot_limits():
    controller = CameraPanController(
        ItoDroidConfig(
            servo_neutral_degrees=90,
            servo_min_degrees=60,
            servo_max_degrees=120,
            yaw_to_servo_degrees_per_radian=30,
        )
    )

    assert controller.target_for_yaw(1) == 120
    assert controller.target_for_yaw(-2) == 60


def test_driver_uses_newest_input_and_times_out_locally():
    clock = FakeClock()
    driver = ItoDroidDriver(
        ItoDroidConfig(pilot_input_timeout_ms=100, servo_smoothing=1), clock=clock
    )
    driver.receive_pilot_input_snapshot({"headsetYawRad": 0.5})
    angle = driver.process_control_tick(1 / 60)
    clock.now = 0.101

    assert driver.process_control_tick(1 / 60) == angle


def test_control_lifecycle_neutralizes_on_start_and_stop():
    async def scenario():
        servo = RecordingServo()
        media = CameraMediaPublisher()
        driver = ItoDroidDriver(
            ItoDroidConfig(), servo_publisher=servo, media_publisher=media
        )
        driver.receive_camera_frame(
            CameraFrame(b"rgb", 1.0, encoding="rgb8", width=1, height=1)
        )
        websocket = FakeWebSocket()

        await driver.handle_control_start(
            websocket,
            make_envelope(TYPE_DRIVER_CONTROL_START, {}, message_id="start"),
        )
        assert driver.control_active is True
        assert media.active is True
        assert websocket.sent[-1]["type"] == TYPE_DRIVER_CONTROL_START_RESULT

        await driver.handle_control_stop(
            websocket,
            make_envelope(TYPE_DRIVER_CONTROL_STOP, {}, message_id="stop"),
        )
        assert driver.control_active is False
        assert media.active is False
        assert servo.angles[-1] == driver.config.servo_neutral_degrees
        assert websocket.sent[-1]["type"] == TYPE_DRIVER_CONTROL_STOP_RESULT

    asyncio.run(scenario())


def test_pilot_input_has_no_session_identity():
    snapshot = decode_pilot_input_snapshot(
        '{"protocolVersion":"ito.v1","sequence":2,"timestampMs":1,'
        '"headsetYawRad":0,"controllers":[]}'
    )

    assert snapshot["sequence"] == 2
    assert "sessionId" not in snapshot
