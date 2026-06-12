import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from time import monotonic

import httpx
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .scene import load_ply, split_scene

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("ito.mock_mono")

DESCRIPTOR = {
    "name": "Mock mono processor",
    "type": "visual-processor",
    "accepts": {"kind": "mono", "encoding": "vp8"},
    "scene": {"format": "ply"},
}
SPLAT_FILE = os.getenv("SPLAT_FILE", "/media/scene.ply")
STALE_SECONDS = 1.0

class Offer(BaseModel):
    type: str
    sdp: str
class SignalRequest(BaseModel):
    purpose: str
    offer: Offer

class ProcessorSession:
    def __init__(self, scene: bytes):
        self.scene = scene
        self.scene_channel = None
        self.status_channel = None
        self.source_pc: RTCPeerConnection | None = None
        self.frames = 0
        self.last_frame_at = 0.0
        self.stale_sent = False

    def status(self, payload: dict):
        if self.status_channel and self.status_channel.readyState == "open":
            self.status_channel.send(json.dumps(payload))

    async def send_scene(self):
        channel = self.scene_channel
        if not channel or channel.readyState != "open":
            return
        chunks = split_scene(self.scene)
        channel.send(json.dumps({"type": "scene-header", "format": "ply", "bytes": len(self.scene), "chunks": len(chunks)}))
        for chunk in chunks:
            while channel.bufferedAmount > 1_000_000:
                await asyncio.sleep(0.01)
            channel.send(chunk)
        log.info("scene_sent bytes=%d chunks=%d", len(self.scene), len(chunks))

    async def connect_source(self, source: dict):
        if self.source_pc:
            await self.source_pc.close()
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.source_pc = pc
        pc.addTransceiver("video", direction="recvonly")
        @pc.on("track")
        def track(track):
            if track.kind == "video":
                asyncio.create_task(self.consume(track))
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(source["url"], json={"purpose": source.get("purpose", "video-source"), "offer": {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}})
            response.raise_for_status()
        answer = response.json()
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
        log.info("connected_video_source url=%s", source["url"])

    async def consume(self, track):
        while True:
            try:
                await track.recv()
            except Exception:
                self.status({"type": "visual-state", "state": "stale", "frames": self.frames})
                return
            self.frames += 1
            self.last_frame_at = monotonic()
            if self.frames == 1:
                self.status({"type": "visual-state", "state": "ready", "frames": 1})
                await self.send_scene()

pcs: set[RTCPeerConnection] = set()
sessions: set[ProcessorSession] = set()
scene_data: bytes | None = None
stale_task: asyncio.Task | None = None

async def stale_monitor():
    while True:
        now = monotonic()
        for session in sessions:
            stale = session.frames > 0 and now - session.last_frame_at > STALE_SECONDS
            if stale and not session.stale_sent:
                session.stale_sent = True
                session.status({"type": "visual-state", "state": "stale", "frames": session.frames})
            elif not stale:
                session.stale_sent = False
        await asyncio.sleep(0.25)

@asynccontextmanager
async def lifespan(_: FastAPI):
    global scene_data, stale_task
    try:
        scene_data = load_ply(SPLAT_FILE)
        log.info("loaded_scene path=%s bytes=%d", SPLAT_FILE, len(scene_data))
    except (OSError, ValueError) as error:
        log.error("scene unavailable: %s", error)
    stale_task = asyncio.create_task(stale_monitor())
    yield
    stale_task.cancel()
    await asyncio.gather(*(pc.close() for pc in list(pcs)), return_exceptions=True)

app = FastAPI(title="Ito mock mono processor", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

@app.get("/")
def descriptor():
    return DESCRIPTOR

@app.post("/webrtc")
async def webrtc(request: SignalRequest):
    if request.purpose != "client":
        raise HTTPException(400, "purpose must be client")
    if scene_data is None:
        raise HTTPException(503, f"scene unavailable; mount SPLAT_FILE at {SPLAT_FILE}")
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    session = ProcessorSession(scene_data)
    pcs.add(pc); sessions.add(session)

    @pc.on("connectionstatechange")
    async def changed():
        log.info("client_peer state=%s", pc.connectionState)
        if pc.connectionState in {"failed", "closed", "disconnected"}:
            sessions.discard(session); pcs.discard(pc)
            if session.source_pc:
                await session.source_pc.close()
            await pc.close()

    @pc.on("datachannel")
    def datachannel(channel):
        if channel.label == "scene":
            session.scene_channel = channel
            @channel.on("message")
            def scene_message(raw):
                with suppress(ValueError, TypeError):
                    if json.loads(raw).get("type") == "resend-scene":
                        asyncio.create_task(session.send_scene())
        elif channel.label == "status":
            session.status_channel = channel
            @channel.on("message")
            def status_message(raw):
                with suppress(ValueError, TypeError, KeyError):
                    message = json.loads(raw)
                    if message.get("type") == "video-source":
                        asyncio.create_task(session.connect_source(message))

    await pc.setRemoteDescription(RTCSessionDescription(sdp=request.offer.sdp, type=request.offer.type))
    answer = await pc.createAnswer(); await pc.setLocalDescription(answer)
    return {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
