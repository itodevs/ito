"""Recorded robot driver exposing looped video and latest-value WebXR control over WebRTC."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .control import ControlState

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("ito.recorded_driver")

DESCRIPTOR = {
    "name": "Recorded robot",
    "type": "robot-driver",
    "modes": ["control", "raw-video"],
    "video": {"kind": "mono", "encoding": "vp8"},
}
VIDEO_FILE = os.getenv("VIDEO_FILE", "/media/robot-video.mp4")
PUBLIC_WEBRTC_URL = os.getenv("PUBLIC_WEBRTC_URL", "http://127.0.0.1:8001/webrtc")


class Offer(BaseModel):
    """Browser or processor SDP offer."""

    type: str
    sdp: str


class SignalRequest(BaseModel):
    """One-shot signaling request with only the current path's configuration."""

    purpose: str
    offer: Offer
    configuration: dict = Field(default_factory=dict)


pcs: set[RTCPeerConnection] = set()
player: MediaPlayer | None = None
relay = MediaRelay()
watchdog_tasks: set[asyncio.Task] = set()


async def wait_for_ice(peer: RTCPeerConnection) -> None:
    """Wait until the SDP answer contains all local host ICE candidates."""
    if peer.iceGatheringState == "complete":
        return

    done = asyncio.Event()

    @peer.on("icegatheringstatechange")
    def changed() -> None:
        if peer.iceGatheringState == "complete":
            done.set()

    await done.wait()


async def watchdog(state: ControlState) -> None:
    """Continuously enforce the final 500 ms active-control timeout."""
    while True:
        state.check_watchdog()
        await asyncio.sleep(0.1)


async def close_peer(peer: RTCPeerConnection, state: ControlState | None = None) -> None:
    """Stop control and release a disconnected peer's resources."""
    if state:
        state.safe_stop("peer-disconnected")
    pcs.discard(peer)
    await peer.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Open the shared looping media source and close peers on shutdown."""
    global player
    if os.path.exists(VIDEO_FILE):
        player = MediaPlayer(VIDEO_FILE, loop=True)
        log.info("video_source file=%s", VIDEO_FILE)
    else:
        log.warning("video file missing at %s; signaling remains available", VIDEO_FILE)

    yield

    for task in list(watchdog_tasks):
        task.cancel()
    await asyncio.gather(*(peer.close() for peer in list(pcs)), return_exceptions=True)


app = FastAPI(title="Ito recorded robot", lifespan=lifespan)


@app.get("/")
def descriptor() -> dict:
    """Describe the recorded driver's small current capability set."""
    return DESCRIPTOR


@app.post("/webrtc")
async def webrtc(request: SignalRequest) -> dict:
    """Create one direct client-control or processor-video peer connection."""
    if request.purpose not in {"client", "video-source"}:
        raise HTTPException(400, "purpose must be client or video-source")
    if not player or not player.video:
        raise HTTPException(503, f"video unavailable; mount VIDEO_FILE at {VIDEO_FILE}")

    log.info(
        "webrtc_offer purpose=%s receive_video=%s sdp_bytes=%d",
        request.purpose,
        request.configuration.get("receiveVideo", False),
        len(request.offer.sdp),
    )
    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    pcs.add(peer)
    state = ControlState() if request.purpose == "client" else None

    @peer.on("connectionstatechange")
    async def connection_changed() -> None:
        log.info("peer purpose=%s state=%s", request.purpose, peer.connectionState)
        if peer.connectionState in {"failed", "closed", "disconnected"}:
            await close_peer(peer, state)

    @peer.on("datachannel")
    def datachannel(channel) -> None:
        log.info("datachannel label=%s", channel.label)
        if not state:
            return

        if channel.label == "status":
            state.status = channel

            @channel.on("message")
            def status_message(raw) -> None:
                with suppress(ValueError, TypeError):
                    message = json.loads(raw)
                    if message.get("type") == "request-video-source":
                        state.send_status({
                            "type": "video-source",
                            "url": PUBLIC_WEBRTC_URL,
                            "purpose": "video-source",
                        })
        elif channel.label == "control":

            @channel.on("message")
            def control_message(raw) -> None:
                with suppress(ValueError, TypeError):
                    state.handle(json.loads(raw))

    await peer.setRemoteDescription(
        RTCSessionDescription(sdp=request.offer.sdp, type=request.offer.type),
    )
    # Processed client sessions need control/status only; raw clients and processors receive video.
    if request.purpose == "video-source" or request.configuration.get("receiveVideo", False):
        peer.addTrack(relay.subscribe(player.video))
    answer = await peer.createAnswer()
    await peer.setLocalDescription(answer)
    await wait_for_ice(peer)

    if state:
        task = asyncio.create_task(watchdog(state))
        watchdog_tasks.add(task)
        task.add_done_callback(watchdog_tasks.discard)

    log.info(
        "webrtc_answer purpose=%s sdp_bytes=%d",
        request.purpose,
        len(peer.localDescription.sdp),
    )
    return {"type": peer.localDescription.type, "sdp": peer.localDescription.sdp}
