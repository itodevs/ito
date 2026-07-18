import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers" / "mock-robot"))

from mock_robot.camera import VideoFileCamera
from mock_robot.config import MockRobotConfig
from mock_robot.driver import MockRobotDriver
from server.ito.protocol import (
    TYPE_DRIVER_CONTROL_START,
    TYPE_DRIVER_CONTROL_START_RESULT,
    TYPE_DRIVER_CONTROL_STOP,
    TYPE_DRIVER_CONTROL_STOP_RESULT,
    TYPE_WEBRTC_OFFER,
    make_envelope,
    unpack_envelope,
)


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(unpack_envelope(frame))


class FakeCameraMediaPublisher:
    def __init__(self):
        self.closed = []

    async def create_offer(self, *, control_key, video_path, loop):
        assert control_key == "control"
        return "camera offer"

    async def close_control(self, control_key):
        self.closed.append(control_key)


def test_video_file_camera_reads_samples(tmp_path):
    video = tmp_path / "camera.h264"
    video.write_bytes(b"abcdef")

    samples = list(VideoFileCamera(video, chunk_size=4, loop=False).samples())

    assert [sample.data for sample in samples] == [b"abcd", b"ef"]


def test_remote_driver_starts_and_stops_without_robot_or_session_identity(tmp_path):
    async def scenario():
        video = tmp_path / "camera.h264"
        video.write_bytes(b"frame")
        publisher = FakeCameraMediaPublisher()
        driver = MockRobotDriver(
            MockRobotConfig(camera_video_path=str(video)),
            camera_media_webrtc=publisher,
        )
        websocket = FakeWebSocket()

        await driver.handle_control_start(
            websocket,
            make_envelope(TYPE_DRIVER_CONTROL_START, {}, message_id="start-1"),
        )
        assert driver.control_active is True
        assert websocket.sent[-2]["type"] == TYPE_DRIVER_CONTROL_START_RESULT
        assert websocket.sent[-1]["type"] == TYPE_WEBRTC_OFFER
        assert "robotId" not in websocket.sent[-1]
        assert "sessionId" not in websocket.sent[-1]

        await driver.handle_control_stop(
            websocket,
            make_envelope(TYPE_DRIVER_CONTROL_STOP, {}, message_id="stop-1"),
        )
        assert driver.control_active is False
        assert websocket.sent[-1]["type"] == TYPE_DRIVER_CONTROL_STOP_RESULT
        assert publisher.closed == ["control"]

    asyncio.run(scenario())
