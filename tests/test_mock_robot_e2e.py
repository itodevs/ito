import asyncio
import json
import logging
import sys
from contextlib import suppress
from pathlib import Path

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

aiortc = pytest.importorskip("aiortc")
av = pytest.importorskip("av")
RTCConfiguration = aiortc.RTCConfiguration
RTCPeerConnection = aiortc.RTCPeerConnection
RTCSessionDescription = aiortc.RTCSessionDescription

ROOT = Path(__file__).resolve().parents[1]
MOCK_DRIVER_ROOT = ROOT / "drivers" / "mock-robot"
sys.path.insert(0, str(MOCK_DRIVER_ROOT))

from mock_robot.config import MockRobotConfig
from mock_robot.driver import MockRobotDriver
from server.ito.app import ItoServer
from server.ito.config import ServerConfig
from server.ito.protocol import (
    ROLE_PILOT_CLIENT,
    TYPE_CATALOG_GET,
    TYPE_CATALOG_GET_RESULT,
    TYPE_CONNECTION_HELLO,
    TYPE_CONNECTION_HELLO_RESULT,
    TYPE_SESSION_ACQUIRE,
    TYPE_SESSION_ACQUIRE_RESULT,
    TYPE_SESSION_END,
    TYPE_WEBRTC_ANSWER,
    TYPE_WEBRTC_OFFER,
    WEBRTC_PATH_PILOT_INPUT,
    make_envelope,
    pack_envelope,
    unpack_envelope,
)


def test_mock_robot_e2e_acquire_and_pilot_input_over_websocket_and_webrtc(tmp_path, caplog):
    asyncio.run(_mock_robot_e2e_acquire_and_pilot_input_over_websocket_and_webrtc(tmp_path, caplog))


async def _mock_robot_e2e_acquire_and_pilot_input_over_websocket_and_webrtc(tmp_path, caplog):
    video = tmp_path / "camera.mp4"
    _write_h264_sample_video(video)
    server = ItoServer(
        ServerConfig(
            host="127.0.0.1",
            port=0,
            request_timeout_ms=3000,
            driver_status_watchdog_ms=1000,
            session_cleanup_timeout_ms=1000,
        )
    )

    async with serve(server._handle_connection, "127.0.0.1", 0) as websocket_server:
        port = websocket_server.sockets[0].getsockname()[1]
        server_url = f"ws://127.0.0.1:{port}"
        driver = MockRobotDriver(
            MockRobotConfig(
                server_url=server_url,
                robot_id="mock-robot-1",
                status_interval_ms=50,
                camera_video_path=str(video),
                camera_loop=False,
            )
        )
        driver_task = asyncio.create_task(driver.run_once())
        peer_connection = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
        try:
            with caplog.at_level(logging.INFO, logger="mock_robot.driver"):
                async with connect(server_url) as pilot_ws:
                    await _send(
                        pilot_ws,
                        make_envelope(
                            TYPE_CONNECTION_HELLO,
                            {"role": ROLE_PILOT_CLIENT},
                            message_id="pilot-hello",
                        ),
                    )
                    hello = await _recv_type(pilot_ws, TYPE_CONNECTION_HELLO_RESULT, "pilot-hello")
                    assert hello["payload"]["ok"] is True

                    await _wait_for_mock_robot_available(pilot_ws)
                    await _send(
                        pilot_ws,
                        make_envelope(
                            TYPE_SESSION_ACQUIRE,
                            {"robotId": "mock-robot-1"},
                            message_id="acquire-mock",
                            robot_id="mock-robot-1",
                        ),
                    )
                    acquired = await _recv_type(pilot_ws, TYPE_SESSION_ACQUIRE_RESULT, "acquire-mock")
                    assert acquired["payload"]["ok"] is True
                    session_id = acquired["payload"]["value"]["sessionId"]
                    await _wait_for_camera_frame(server, session_id)

                    data_channel = peer_connection.createDataChannel(
                        "ito.pilotInput",
                        ordered=False,
                        maxRetransmits=0,
                    )
                    offer = await peer_connection.createOffer()
                    await peer_connection.setLocalDescription(offer)
                    await _wait_for_ice_gathering_complete(peer_connection)
                    await _send(
                        pilot_ws,
                        make_envelope(
                            TYPE_WEBRTC_OFFER,
                            {"path": WEBRTC_PATH_PILOT_INPUT, "sdp": peer_connection.localDescription.sdp},
                            message_id="pilot-input-offer",
                            robot_id="mock-robot-1",
                            session_id=session_id,
                        ),
                    )
                    answer = await _recv_type(pilot_ws, TYPE_WEBRTC_ANSWER, "pilot-input-offer")
                    assert answer["payload"]["path"] == WEBRTC_PATH_PILOT_INPUT
                    await peer_connection.setRemoteDescription(
                        RTCSessionDescription(sdp=answer["payload"]["sdp"], type="answer")
                    )
                    await _wait_for_data_channel_open(data_channel)

                    snapshot = {
                        "protocolVersion": "ito.v1",
                        "sessionId": session_id,
                        "sequence": 1,
                        "timestampMs": 12345,
                        "headsetYawRad": 0.42,
                        "controllers": {"left": {}, "right": {"triggerPressed": True}},
                    }
                    data_channel.send(json.dumps(snapshot))
                    await _wait_for_log(caplog, '"headsetYawRad": 0.42')

                    await _send(
                        pilot_ws,
                        make_envelope(
                            TYPE_SESSION_END,
                            {"reason": {"code": "session.ended.pilot_requested"}, "clean": True},
                            message_id="end-mock",
                            robot_id="mock-robot-1",
                            session_id=session_id,
                        ),
                    )
                    await _recv_type(pilot_ws, "session.end.result", "end-mock")
        finally:
            await peer_connection.close()
            driver_task.cancel()
            with suppress(asyncio.CancelledError):
                await driver_task


async def _wait_for_mock_robot_available(pilot_ws):
    for attempt in range(20):
        message_id = f"catalog-{attempt}"
        await _send(
            pilot_ws,
            make_envelope(TYPE_CATALOG_GET, {"includeUnavailable": True}, message_id=message_id),
        )
        catalog = await _recv_type(pilot_ws, TYPE_CATALOG_GET_RESULT, message_id)
        robots = catalog["payload"]["value"]["robots"]
        if robots and robots[0]["robotId"] == "mock-robot-1" and robots[0]["status"] == "Available":
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Mock Robot did not become available in the catalog")


async def _send(websocket, envelope):
    await websocket.send(pack_envelope(envelope))


async def _recv_type(websocket, message_type, reply_to):
    for _ in range(20):
        envelope = unpack_envelope(await asyncio.wait_for(websocket.recv(), timeout=3))
        if envelope["type"] == message_type and envelope.get("replyToMessageId") == reply_to:
            return envelope
    raise AssertionError(f"Did not receive {message_type} replying to {reply_to}")


async def _wait_for_data_channel_open(data_channel):
    if data_channel.readyState == "open":
        return
    opened = asyncio.Event()

    @data_channel.on("open")
    def on_open():
        opened.set()

    await asyncio.wait_for(opened.wait(), timeout=5)


async def _wait_for_ice_gathering_complete(peer_connection):
    if peer_connection.iceGatheringState == "complete":
        return
    complete = asyncio.Event()

    @peer_connection.on("icegatheringstatechange")
    def on_ice_gathering_state_change():
        if peer_connection.iceGatheringState == "complete":
            complete.set()

    await asyncio.wait_for(complete.wait(), timeout=5)


async def _wait_for_log(caplog, text):
    for _ in range(50):
        if text in caplog.text:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"Did not find log text: {text}")


def _write_h264_sample_video(path):
    try:
        container = av.open(str(path), mode="w")
        stream = container.add_stream("libx264", rate=5)
        stream.width = 16
        stream.height = 16
        stream.pix_fmt = "yuv420p"
        for index in range(3):
            frame = av.VideoFrame(16, 16, "yuv420p")
            frame.planes[0].update(bytes([32 + index * 20]) * frame.planes[0].buffer_size)
            frame.planes[1].update(bytes([128]) * frame.planes[1].buffer_size)
            frame.planes[2].update(bytes([128]) * frame.planes[2].buffer_size)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        container.close()
    except Exception as exc:
        pytest.skip(f"local PyAV/FFmpeg cannot create an H.264 sample video: {exc}")


async def _wait_for_camera_frame(server, session_id):
    for _ in range(80):
        runtime = server.reconstruction_runtimes.get(session_id)
        processor = getattr(runtime, "processor", None)
        if getattr(processor, "frame_count", 0) > 0:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("cameraMedia did not deliver a decoded frame to reconstruction")
