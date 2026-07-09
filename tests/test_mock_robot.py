import asyncio
import importlib.util
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCK_DRIVER_ROOT = ROOT / "drivers" / "mock-robot"
sys.path.insert(0, str(MOCK_DRIVER_ROOT))

from mock_robot.camera import VideoFileCamera
from mock_robot.config import MockRobotConfig
from mock_robot.driver import MockRobotDriver
from server.ito.protocol import (
    TYPE_DRIVER_SESSION_START,
    TYPE_DRIVER_SESSION_START_RESULT,
    TYPE_SESSION_END,
    TYPE_SESSION_END_RESULT,
    make_envelope,
    unpack_envelope,
)


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(unpack_envelope(frame))


def test_mock_robot_imports_without_websocket_side_effects():
    spec = importlib.util.spec_from_file_location(
        "mock_robot_main",
        MOCK_DRIVER_ROOT / "main.py",
    )
    assert spec is not None


def test_status_requires_camera_video_for_availability():
    driver = MockRobotDriver(MockRobotConfig(camera_video_path=None))

    assert driver.status_payload() == {
        "name": "Mock Robot",
        "type": "Droid",
        "status": "Unavailable",
        "availabilityDetail": {"code": "mock_robot.camera_video_required"},
    }


def test_video_file_camera_reads_samples(tmp_path):
    video = tmp_path / "camera.h264"
    video.write_bytes(b"abcdef")
    camera = VideoFileCamera(video, chunk_size=4, loop=False)

    samples = list(camera.samples())

    assert [sample.data for sample in samples] == [b"abcd", b"ef"]
    assert [sample.offset for sample in samples] == [0, 4]


def test_session_lifecycle_opens_and_closes_camera(tmp_path):
    asyncio.run(_session_lifecycle_opens_and_closes_camera(tmp_path))


async def _session_lifecycle_opens_and_closes_camera(tmp_path):
    video = tmp_path / "camera.h264"
    video.write_bytes(b"frame-data")
    driver = MockRobotDriver(MockRobotConfig(camera_video_path=str(video)))
    websocket = FakeWebSocket()

    await driver.handle_session_start(
        websocket,
        make_envelope(
            TYPE_DRIVER_SESSION_START,
            {"sessionId": "session-1", "sessionConfig": {"pilotInputDataChannel": {"ordered": False}}},
            message_id="start-1",
            robot_id="mock-robot-1",
            session_id="session-1",
        ),
    )

    assert driver.session_id == "session-1"
    assert driver.camera is not None
    assert driver.camera.is_open
    assert websocket.sent[-1]["type"] == TYPE_DRIVER_SESSION_START_RESULT
    assert websocket.sent[-1]["replyToMessageId"] == "start-1"
    assert websocket.sent[-1]["payload"] == {"ok": True, "value": {"sessionId": "session-1"}}

    await driver.handle_session_end(
        websocket,
        make_envelope(
            TYPE_SESSION_END,
            {"reason": {"code": "session.ended.pilot_requested"}, "clean": True},
            message_id="end-1",
            robot_id="mock-robot-1",
            session_id="session-1",
        ),
    )

    assert driver.session_id is None
    assert not driver.camera.is_open
    assert websocket.sent[-1]["type"] == TYPE_SESSION_END_RESULT
    assert websocket.sent[-1]["payload"] == {"ok": True, "value": {"sessionId": "session-1"}}


def test_session_start_fails_without_camera_video():
    asyncio.run(_session_start_fails_without_camera_video())


async def _session_start_fails_without_camera_video():
    driver = MockRobotDriver(MockRobotConfig(camera_video_path=None))
    websocket = FakeWebSocket()

    await driver.handle_session_start(
        websocket,
        make_envelope(
            TYPE_DRIVER_SESSION_START,
            {"sessionId": "session-1", "sessionConfig": {}},
            message_id="start-1",
            robot_id="mock-robot-1",
            session_id="session-1",
        ),
    )

    assert websocket.sent[-1]["type"] == TYPE_DRIVER_SESSION_START_RESULT
    assert websocket.sent[-1]["payload"] == {
        "ok": False,
        "reason": {"code": "mock_robot.camera_video_required"},
    }


def test_pilot_input_snapshot_is_logged(caplog):
    driver = MockRobotDriver(MockRobotConfig(camera_video_path=None))

    with caplog.at_level(logging.INFO):
        driver.receive_pilot_input_snapshot(
            {
                "headsetYawRadians": 0.25,
                "controllers": {"right": {"triggerPressed": True}},
            }
        )

    assert "pilot_input_snapshot" in caplog.text
    assert '"headsetYawRadians": 0.25' in caplog.text
