from server.ito.media import AiortcCameraTrackReceiver
from server.ito.reconstruction import ReconstructionRuntime
from server.ito.splat import decode_splat_batch_header, encode_splat_batch
from server.ito.webrtc import SplatBatchChannel, decode_pilot_input_snapshot
from server.processors.base import GaussianSplat, ProcessorSplatBatch, ReconstructionFrame


def test_pilot_input_decoder_has_no_session_identity():
    snapshot = decode_pilot_input_snapshot(
        b'{"protocolVersion":"ito.v1","sequence":1,"timestampMs":12,'
        b'"headsetYawRad":0.25,"controllers":[]}'
    )

    assert snapshot["sequence"] == 1
    assert "sessionId" not in snapshot


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

    assert header.sequence == 7
    assert header.splat_count == 1
    assert len(payload) == 28 + header.record_stride


class FailingProcessor:
    capture_modality = "monocularRgb"

    def start(self):
        pass

    def process_frame(self, frame):
        raise RuntimeError("boom")

    def reset(self):
        pass

    def close(self):
        pass


def test_reconstruction_failure_is_reported_without_raising():
    failures = []
    runtime = ReconstructionRuntime(
        FailingProcessor(),
        send_splat_batch=lambda payload: None,
        fail_control=failures.append,
    )
    runtime.start()

    runtime.process_frame(ReconstructionFrame(b"rgb", 1, 1, 1))
    runtime.process_frame(ReconstructionFrame(b"rgb", 2, 1, 1))

    assert failures == [{"code": "control.stopped.reconstruction_failed"}]


def test_camera_track_receiver_converts_video_frames_for_reconstruction():
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

    frame = AiortcCameraTrackReceiver(lambda value: None)._reconstruction_frame(Frame())

    assert frame.data == b"rgb"
    assert frame.timestamp_ms == 1000


def test_splat_channel_sends_only_when_open():
    class Channel:
        readyState = "open"

        def __init__(self):
            self.sent = []

        def send(self, payload):
            self.sent.append(payload)

    registry = SplatBatchChannel()
    channel = Channel()
    registry.attach(channel)

    assert registry.send(b"batch") is True
    assert channel.sent == [b"batch"]
