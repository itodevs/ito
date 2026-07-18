import asyncio
from contextlib import suppress
import sys
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers" / "mock-robot"))

from mock_robot.config import MockRobotConfig
from mock_robot.driver import MockRobotDriver
from server.ito.app import ItoApplication
from server.ito.config import ItoConfig
from server.ito.protocol import (
    ROLE_PILOT_CLIENT,
    TYPE_CONNECTION_HELLO,
    TYPE_CONTROL_START,
    TYPE_CONTROL_START_RESULT,
    TYPE_CONTROL_STOP,
    TYPE_CONTROL_STOP_RESULT,
    make_envelope,
    pack_envelope,
    unpack_envelope,
)
from server.ito.robot import RemoteRobotAdapter


class FakeCameraPublisher:
    async def create_offer(self, **_kwargs):
        return "camera offer"

    async def accept_answer(self, **_kwargs):
        pass

    async def close_control(self, _control_key):
        pass


class FakeLivePaths:
    async def accept_offer(self, *, path, control_key, sdp):
        assert control_key == "control"
        assert path == "cameraMedia"
        assert sdp == "camera offer"
        return "camera answer"

    async def close_control(self, _control_key):
        pass


def test_external_mode_keeps_the_same_direct_pilot_lifecycle(tmp_path):
    asyncio.run(_external_mode_keeps_the_same_direct_pilot_lifecycle(tmp_path))


async def _external_mode_keeps_the_same_direct_pilot_lifecycle(tmp_path):
    video = tmp_path / "camera.h264"
    video.write_bytes(b"camera")
    adapter = RemoteRobotAdapter(request_timeout_ms=1000)
    application = ItoApplication(
        ItoConfig(host="127.0.0.1", port=1, robot_backend="remote"),
        adapter=adapter,
    )
    application.live_paths = FakeLivePaths()

    async with serve(application._handle_connection, "127.0.0.1", 0) as websocket_server:
        port = websocket_server.sockets[0].getsockname()[1]
        driver = MockRobotDriver(
            MockRobotConfig(ito_url=f"ws://127.0.0.1:{port}", camera_video_path=str(video)),
            camera_media_webrtc=FakeCameraPublisher(),
        )
        driver_task = asyncio.create_task(driver.run_once())
        try:
            for _ in range(20):
                if adapter.ready:
                    break
                await asyncio.sleep(0.01)
            assert adapter.ready

            async with connect(f"ws://127.0.0.1:{port}") as pilot:
                await pilot.send(
                    pack_envelope(
                        make_envelope(
                            TYPE_CONNECTION_HELLO,
                            {"role": ROLE_PILOT_CLIENT},
                            message_id="hello",
                        )
                    )
                )
                hello = unpack_envelope(await pilot.recv())
                assert hello["payload"]["value"]["robotReady"] is True

                await pilot.send(
                    pack_envelope(
                        make_envelope(TYPE_CONTROL_START, {}, message_id="start")
                    )
                )
                started = await _receive_reply(pilot, TYPE_CONTROL_START_RESULT, "start")
                assert started["payload"]["ok"] is True

                await pilot.send(
                    pack_envelope(
                        make_envelope(TYPE_CONTROL_STOP, {}, message_id="stop")
                    )
                )
                stopped = await _receive_reply(pilot, TYPE_CONTROL_STOP_RESULT, "stop")
                assert stopped["payload"]["ok"] is True
        finally:
            driver_task.cancel()
            with suppress(asyncio.CancelledError):
                await driver_task


async def _receive_reply(websocket, message_type, reply_to):
    for _ in range(10):
        envelope = unpack_envelope(await asyncio.wait_for(websocket.recv(), timeout=2))
        if envelope["type"] == message_type and envelope.get("replyToMessageId") == reply_to:
            return envelope
    raise AssertionError(f"missing {message_type}")
