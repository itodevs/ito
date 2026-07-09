import asyncio

from server.ito.app import ItoServer
from server.ito.config import ServerConfig
from server.ito.protocol import (
    ROLE_PILOT_CLIENT,
    TYPE_WEBRTC_ANSWER,
    TYPE_WEBRTC_OFFER,
    WEBRTC_PATH_CAMERA_MEDIA,
    WEBRTC_PATH_PILOT_INPUT,
    WEBRTC_PATH_SPLAT_BATCHES,
    make_envelope,
    pack_envelope,
    unpack_envelope,
)
from server.ito.reconstruction import ReconstructionSessionRuntime
from server.ito.media import AiortcCameraTrackReceiver
from server.ito.splat import decode_splat_batch_header, encode_splat_batch
from server.ito.webrtc import SplatBatchChannelRegistry
from server.processors.base import GaussianSplat, ProcessorSplatBatch, ReconstructionFrame

from tests.test_server_app import (
    acquire_task,
    answer_driver_start,
    hello_available_driver,
    hello_pilot,
    state,
)


class FakeLivePaths:
    def __init__(self):
        self.offers = []

    async def accept_offer(self, *, path, session_id, sdp):
        self.offers.append({"path": path, "sessionId": session_id, "sdp": sdp})
        return f"answer for {path}"


def test_pilot_input_webrtc_offer_is_relayed_and_answer_is_routed_back():
    asyncio.run(_pilot_input_webrtc_offer_is_relayed_and_answer_is_routed_back())


async def _pilot_input_webrtc_offer_is_relayed_and_answer_is_routed_back():
    server = ItoServer(ServerConfig(request_timeout_ms=1000, driver_status_watchdog_ms=1000))
    driver = state()
    pilot = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, pilot)
    task = await acquire_task(server, pilot)
    await asyncio.sleep(0)
    session_id = await answer_driver_start(server, driver)
    await task

    await server._handle_frame(
        pilot,
        pack_envelope(
            make_envelope(
                TYPE_WEBRTC_OFFER,
                {"path": WEBRTC_PATH_PILOT_INPUT, "sdp": "pilot offer"},
                message_id="pilot-offer",
                robot_id="droid-1",
                session_id=session_id,
            )
        ),
    )

    forwarded = driver.websocket.sent[-1]
    assert forwarded["type"] == TYPE_WEBRTC_OFFER
    assert forwarded["payload"] == {"path": WEBRTC_PATH_PILOT_INPUT, "sdp": "pilot offer"}

    await server._handle_frame(
        driver,
        pack_envelope(
            make_envelope(
                TYPE_WEBRTC_ANSWER,
                {"path": WEBRTC_PATH_PILOT_INPUT, "sdp": "driver answer"},
                reply_to_message_id=forwarded["messageId"],
                robot_id="droid-1",
                session_id=session_id,
            )
        ),
    )

    answer = pilot.websocket.sent[-1]
    assert answer["type"] == TYPE_WEBRTC_ANSWER
    assert answer["replyToMessageId"] == "pilot-offer"
    assert answer["payload"] == {"path": WEBRTC_PATH_PILOT_INPUT, "sdp": "driver answer"}


def test_server_terminated_webrtc_offer_returns_non_trickle_answer():
    asyncio.run(_server_terminated_webrtc_offer_returns_non_trickle_answer())


async def _server_terminated_webrtc_offer_returns_non_trickle_answer():
    server = ItoServer(ServerConfig(request_timeout_ms=1000, driver_status_watchdog_ms=1000))
    server.live_paths = FakeLivePaths()
    driver = state()
    pilot = state()
    await hello_available_driver(server, driver)
    await hello_pilot(server, pilot)
    task = await acquire_task(server, pilot)
    await asyncio.sleep(0)
    session_id = await answer_driver_start(server, driver)
    await task

    await server._handle_frame(
        pilot,
        pack_envelope(
            make_envelope(
                TYPE_WEBRTC_OFFER,
                {"path": WEBRTC_PATH_SPLAT_BATCHES, "sdp": "splat offer"},
                message_id="splat-offer",
                session_id=session_id,
            )
        ),
    )

    answer = pilot.websocket.sent[-1]
    assert answer["type"] == TYPE_WEBRTC_ANSWER
    assert answer["replyToMessageId"] == "splat-offer"
    assert answer["payload"] == {"path": WEBRTC_PATH_SPLAT_BATCHES, "sdp": "answer for splatBatches"}

    await server._handle_frame(
        driver,
        pack_envelope(
            make_envelope(
                TYPE_WEBRTC_OFFER,
                {"path": WEBRTC_PATH_CAMERA_MEDIA, "sdp": "camera offer"},
                message_id="camera-offer",
                robot_id="droid-1",
                session_id=session_id,
            )
        ),
    )

    assert server.live_paths.offers[-1] == {
        "path": WEBRTC_PATH_CAMERA_MEDIA,
        "sessionId": session_id,
        "sdp": "camera offer",
    }
    assert driver.websocket.sent[-1]["payload"] == {
        "path": WEBRTC_PATH_CAMERA_MEDIA,
        "sdp": "answer for cameraMedia",
    }


def test_splat_batch_encoder_header_and_size():
    batch = ProcessorSplatBatch(
        sequence=7,
        splats=[
            GaussianSplat(
                position=(1.0, 2.0, 3.0),
                scale=(0.1, 0.2, 0.3),
                rotation=(0.0, 0.0, 0.0, 1.0),
                color=(255, 128, 0, 200),
            )
        ],
    )

    payload = encode_splat_batch(batch)
    header = decode_splat_batch_header(payload)

    assert header.version == 1
    assert header.sequence == 7
    assert header.splat_count == 1
    assert len(payload) == 28 + header.record_stride


class FailingProcessor:
    capture_modality = "monocularRgb"

    def start(self, session_id):
        self.session_id = session_id

    def process_frame(self, frame):
        raise RuntimeError("boom")

    def reset(self):
        pass

    def close(self):
        pass


def test_reconstruction_failure_is_reported_without_raising():
    failures = []
    runtime = ReconstructionSessionRuntime(
        "session-1",
        FailingProcessor(),
        send_splat_batch=lambda payload: None,
        fail_session=failures.append,
    )
    runtime.start()

    runtime.process_frame(ReconstructionFrame(b"rgb", 1, 1, 1))
    runtime.process_frame(ReconstructionFrame(b"rgb", 2, 1, 1))

    assert failures == [{"code": "session.ended.reconstruction_failed"}]


def test_aiortc_camera_track_receiver_converts_video_frames_to_reconstruction_frames():
    class Plane:
        def __bytes__(self):
            return b"rgb"

    class Frame:
        pts = 2
        time_base = 0.5
        width = 1
        height = 1
        planes = [Plane()]

        def to_rgb(self):
            return self

    frames = []
    receiver = AiortcCameraTrackReceiver(frames.append)

    frame = receiver._reconstruction_frame(Frame())

    assert frame.data == b"rgb"
    assert frame.timestamp_ms == 1000
    assert frame.width == 1
    assert frame.height == 1
    assert frame.pixel_format == "rgb24"
    assert frame.sequence == 1


def test_splat_batch_channel_registry_sends_only_when_open():
    class Channel:
        readyState = "open"

        def __init__(self):
            self.sent = []

        def send(self, payload):
            self.sent.append(payload)

    registry = SplatBatchChannelRegistry()
    channel = Channel()

    assert registry.send("session-1", b"batch") is False
    registry.attach("session-1", channel)
    assert registry.send("session-1", b"batch") is True
    assert channel.sent == [b"batch"]
    registry.detach("session-1", channel)
    assert registry.send("session-1", b"batch") is False
