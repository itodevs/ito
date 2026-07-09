import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DROID_DRIVER_ROOT = ROOT / "drivers" / "ito-droid"
sys.path.insert(0, str(DROID_DRIVER_ROOT))

from ito_droid.config import ItoDroidConfig
from ito_droid.control import CameraPanController
from ito_droid.driver import ItoDroidDriver
from ito_droid.media import CameraMediaPublisher
from ito_droid.ros_io import CameraFrame
from ito_droid.webrtc import PilotInputDataChannelReceiver, decode_pilot_input_snapshot
from server.ito.protocol import (
    TYPE_DRIVER_SESSION_START,
    TYPE_DRIVER_SESSION_START_RESULT,
    TYPE_SESSION_END,
    TYPE_SESSION_END_RESULT,
    make_envelope,
    unpack_envelope,
)


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RecordingServo:
    def __init__(self):
        self.angles = []

    def publish_angle(self, angle_degrees):
        self.angles.append(angle_degrees)


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(unpack_envelope(frame))


def test_config_reads_environment(monkeypatch):
    monkeypatch.setenv("ITO_SERVER_URL", "ws://server.example/ws")
    monkeypatch.setenv("ITO_DROID_ROBOT_ID", "droid-a")
    monkeypatch.setenv("ITO_DROID_ROS_CAMERA_TOPIC", "/camera/image")
    monkeypatch.setenv("ITO_DROID_CONTROL_TICK_HZ", "30")
    monkeypatch.setenv("ITO_DROID_SERVO_MIN_DEGREES", "10")

    config = ItoDroidConfig.from_env()

    assert config.server_url == "ws://server.example/ws"
    assert config.robot_id == "droid-a"
    assert config.ros_camera_topic == "/camera/image"
    assert config.control_tick_hz == 30
    assert config.servo_min_degrees == 10


def test_yaw_to_camera_pan_mapping_clamps_to_servo_limits():
    config = ItoDroidConfig(
        servo_neutral_degrees=90,
        servo_min_degrees=60,
        servo_max_degrees=120,
        yaw_to_servo_degrees_per_radian=30,
    )
    controller = CameraPanController(config)

    assert controller.target_for_yaw(0) == 90
    assert controller.target_for_yaw(1) == 120
    assert controller.target_for_yaw(-2) == 60


def test_control_tick_uses_newest_snapshot_and_holds_on_timeout():
    config = ItoDroidConfig(
        pilot_input_timeout_ms=100,
        servo_smoothing=1,
        servo_max_velocity_degrees_per_second=1000,
    )
    clock = FakeClock()
    controller = CameraPanController(config)

    controller.receive_snapshot({"headsetYawRadians": 0.5}, clock())
    angle = controller.tick(clock(), 1 / 60)
    assert angle > config.servo_neutral_degrees

    held_angle = angle
    clock.advance(0.101)
    assert controller.tick(clock(), 1 / 60) == held_angle


def test_safe_resumption_ramps_correction_velocity_after_timeout():
    config = ItoDroidConfig(
        pilot_input_timeout_ms=100,
        servo_smoothing=1,
        servo_max_velocity_degrees_per_second=100,
        resumption_initial_velocity_degrees_per_second=10,
        resumption_ramp_duration_ms=1000,
    )
    clock = FakeClock()
    controller = CameraPanController(config)

    controller.receive_snapshot({"headsetYawRadians": 0}, clock())
    assert controller.tick(clock(), 0.1) == config.servo_neutral_degrees

    clock.advance(0.101)
    assert controller.tick(clock(), 0.1) == config.servo_neutral_degrees

    controller.receive_snapshot({"headsetYawRadians": 1}, clock())
    resumed_angle = controller.tick(clock(), 0.1)
    assert resumed_angle == config.servo_neutral_degrees + 1

    clock.advance(1.0)
    controller.receive_snapshot({"headsetYawRadians": 1}, clock())
    later_angle = controller.tick(clock(), 0.1)
    assert later_angle > resumed_angle + 1


def test_status_reports_unavailable_until_camera_feed_arrives():
    driver = ItoDroidDriver(ItoDroidConfig())

    assert driver.status_payload() == {
        "name": "Ito Droid",
        "type": "Droid",
        "status": "Unavailable",
        "availabilityDetail": {"code": "ito_droid.camera_feed_missing"},
    }

    driver.receive_camera_frame(CameraFrame(b"rgb", 1.0, encoding="rgb8", width=1, height=1))

    assert driver.status_payload() == {
        "name": "Ito Droid",
        "type": "Droid",
        "status": "Available",
    }


def test_ros_camera_frames_flow_to_camera_media_publisher():
    publisher = CameraMediaPublisher()
    driver = ItoDroidDriver(ItoDroidConfig(), media_publisher=publisher)

    publisher.start("session-1")
    frame = CameraFrame(b"frame", 1.0, encoding="rgb8", width=2, height=2)
    driver.receive_camera_frame(frame)

    assert publisher.frame_count == 1
    assert publisher.last_frame == frame


def test_session_start_neutralizes_servo_and_starts_media():
    asyncio.run(_session_start_neutralizes_servo_and_starts_media())


async def _session_start_neutralizes_servo_and_starts_media():
    servo = RecordingServo()
    media = CameraMediaPublisher()
    driver = ItoDroidDriver(ItoDroidConfig(), servo_publisher=servo, media_publisher=media)
    driver.camera_ready = True
    websocket = FakeWebSocket()

    await driver.handle_session_start(
        websocket,
        make_envelope(
            TYPE_DRIVER_SESSION_START,
            {"sessionId": "session-1", "sessionConfig": {"cameraMedia": {"codec": "H264"}}},
            message_id="start-1",
            robot_id="ito-droid-1",
            session_id="session-1",
        ),
    )

    assert driver.session_id == "session-1"
    assert servo.angles == [driver.config.servo_neutral_degrees]
    assert media.started_session_id == "session-1"
    assert websocket.sent[-1]["type"] == TYPE_DRIVER_SESSION_START_RESULT
    assert websocket.sent[-1]["replyToMessageId"] == "start-1"
    assert websocket.sent[-1]["payload"] == {"ok": True, "value": {"sessionId": "session-1"}}


def test_session_start_fails_without_camera_feed():
    asyncio.run(_session_start_fails_without_camera_feed())


async def _session_start_fails_without_camera_feed():
    driver = ItoDroidDriver(ItoDroidConfig())
    websocket = FakeWebSocket()

    await driver.handle_session_start(
        websocket,
        make_envelope(
            TYPE_DRIVER_SESSION_START,
            {"sessionId": "session-1", "sessionConfig": {}},
            message_id="start-1",
            robot_id="ito-droid-1",
            session_id="session-1",
        ),
    )

    assert websocket.sent[-1]["type"] == TYPE_DRIVER_SESSION_START_RESULT
    assert websocket.sent[-1]["payload"] == {
        "ok": False,
        "reason": {"code": "ito_droid.camera_feed_missing"},
    }


def test_clean_session_end_neutralizes_servo_and_stops_media():
    asyncio.run(_clean_session_end_neutralizes_servo_and_stops_media())


def test_pilot_input_data_channel_receiver_decodes_snapshot_json():
    received = []

    class FakeDataChannel:
        def on(self, event):
            assert event == "message"

            def register(callback):
                self.callback = callback
                return callback

            return register

    channel = FakeDataChannel()
    receiver = PilotInputDataChannelReceiver(received.append)
    receiver.attach(channel)
    channel.callback(
        b'{"protocolVersion":"ito.v1","sessionId":"session-1","sequence":1,"headsetYawRad":0.25}'
    )

    assert received == [
        {
            "protocolVersion": "ito.v1",
            "sessionId": "session-1",
            "sequence": 1,
            "headsetYawRad": 0.25,
        }
    ]
    assert decode_pilot_input_snapshot(
        '{"protocolVersion":"ito.v1","sessionId":"session-1","sequence":2,"headsetYawRad":0}'
    )["sequence"] == 2


async def _clean_session_end_neutralizes_servo_and_stops_media():
    servo = RecordingServo()
    media = CameraMediaPublisher()
    driver = ItoDroidDriver(ItoDroidConfig(), servo_publisher=servo, media_publisher=media)
    driver.camera_ready = True
    websocket = FakeWebSocket()

    await driver.handle_session_start(
        websocket,
        make_envelope(
            TYPE_DRIVER_SESSION_START,
            {"sessionId": "session-1", "sessionConfig": {}},
            message_id="start-1",
            robot_id="ito-droid-1",
            session_id="session-1",
        ),
    )
    driver.receive_pilot_input_snapshot({"headsetYawRadians": 0.5})
    driver.process_control_tick(1 / 60)

    await driver.handle_session_end(
        websocket,
        make_envelope(
            TYPE_SESSION_END,
            {"reason": {"code": "session.ended.pilot_requested"}, "clean": True},
            message_id="end-1",
            robot_id="ito-droid-1",
            session_id="session-1",
        ),
    )

    assert driver.session_id is None
    assert media.started_session_id is None
    assert servo.angles[-1] == driver.config.servo_neutral_degrees
    assert websocket.sent[-1]["type"] == TYPE_SESSION_END_RESULT
    assert websocket.sent[-1]["payload"] == {"ok": True, "value": {"sessionId": "session-1"}}
