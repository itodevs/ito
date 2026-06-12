import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
PUBLIC_WEBRTC_URL = os.getenv("PUBLIC_WEBRTC_URL", "http://localhost:8001/webrtc")

class Offer(BaseModel):
    type: str
    sdp: str

class SignalRequest(BaseModel):
    purpose: str
    offer: Offer

pcs: set[RTCPeerConnection] = set()
player: MediaPlayer | None = None
relay = MediaRelay()
watchdog_tasks: set[asyncio.Task] = set()

async def wait_for_ice(pc: RTCPeerConnection):
    if pc.iceGatheringState == "complete":
        return
    done = asyncio.Event()
    @pc.on("icegatheringstatechange")
    def changed():
        if pc.iceGatheringState == "complete":
            done.set()
    await done.wait()

async def watchdog(state: ControlState):
    while True:
        state.check_watchdog()
        await asyncio.sleep(0.1)

async def close_peer(pc: RTCPeerConnection, state: ControlState | None = None):
    if state:
        state.safe_stop("peer-disconnected")
    pcs.discard(pc)
    await pc.close()

@asynccontextmanager
async def lifespan(_: FastAPI):
    global player
    if os.path.exists(VIDEO_FILE):
        player = MediaPlayer(VIDEO_FILE, loop=True)
        log.info("video_source file=%s", VIDEO_FILE)
    else:
        log.warning("video file missing at %s; signaling remains available", VIDEO_FILE)
    yield
    for task in list(watchdog_tasks):
        task.cancel()
    await asyncio.gather(*(pc.close() for pc in list(pcs)), return_exceptions=True)

app = FastAPI(title="Ito recorded robot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

@app.get("/")
def descriptor():
    return DESCRIPTOR

@app.post("/webrtc")
async def webrtc(request: SignalRequest):
    if request.purpose not in {"client", "video-source"}:
        raise HTTPException(400, "purpose must be client or video-source")
    if not player or not player.video:
        raise HTTPException(503, f"video unavailable; mount VIDEO_FILE at {VIDEO_FILE}")
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    pcs.add(pc)
    state = ControlState() if request.purpose == "client" else None

    @pc.on("connectionstatechange")
    async def connection_changed():
        log.info("peer purpose=%s state=%s", request.purpose, pc.connectionState)
        if pc.connectionState in {"failed", "closed", "disconnected"}:
            await close_peer(pc, state)

    @pc.on("datachannel")
    def datachannel(channel):
        log.info("datachannel label=%s", channel.label)
        if not state:
            return
        if channel.label == "status":
            state.status = channel
            @channel.on("message")
            def status_message(raw):
                with suppress(ValueError, TypeError):
                    message = json.loads(raw)
                    if message.get("type") == "request-video-source":
                        state.send_status({"type": "video-source", "url": PUBLIC_WEBRTC_URL, "purpose": "video-source"})
        elif channel.label == "control":
            @channel.on("message")
            def control_message(raw):
                with suppress(ValueError, TypeError):
                    state.handle(json.loads(raw))

    await pc.setRemoteDescription(RTCSessionDescription(sdp=request.offer.sdp, type=request.offer.type))
    pc.addTrack(relay.subscribe(player.video))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    await wait_for_ice(pc)
    if state:
        task = asyncio.create_task(watchdog(state))
        watchdog_tasks.add(task)
        task.add_done_callback(watchdog_tasks.discard)
    return {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
