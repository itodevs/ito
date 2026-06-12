"""Mock mono processor proving direct video consumption and streamed Gaussian-splat output."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from time import monotonic

import httpx
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .scene import iter_splat_chunks, load_splat_ply

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("ito.mock_mono")

DESCRIPTOR = {
    "name": "Mock mono processor",
    "type": "visual-processor",
    "accepts": {"kind": "mono", "encoding": "vp8"},
    "scene": {"format": "gaussian-splat-stream", "encoding": "ply"},
}
SPLAT_FILE = os.getenv("SPLAT_FILE", "/media/scene.ply")
STALE_SECONDS = 1.0


class Offer(BaseModel):
    """Client SDP offer."""

    type: str
    sdp: str


class SignalRequest(BaseModel):
    """One-shot client signaling request."""

    purpose: str
    offer: Offer


async def wait_for_ice(peer: RTCPeerConnection) -> None:
    """Wait until a local SDP description includes all host ICE candidates."""
    if peer.iceGatheringState == "complete":
        return

    done = asyncio.Event()

    @peer.on("icegatheringstatechange")
    def changed() -> None:
        if peer.iceGatheringState == "complete":
            done.set()

    await done.wait()


class ProcessorSession:
    """Hold the two direct peers and one client splat stream for a processed session."""

    def __init__(self, splat_data: bytes):
        self.splat_data = splat_data
        self.scene_channel = None
        self.status_channel = None
        self.source_peer: RTCPeerConnection | None = None
        self.frames = 0
        self.last_frame_at = 0.0
        self.stale_sent = False

    def status(self, payload: dict) -> None:
        """Send useful processor state when the reliable status channel is open."""
        if self.status_channel and self.status_channel.readyState == "open":
            self.status_channel.send(json.dumps(payload))

    async def send_splats(self) -> None:
        """Stream a header followed by ordered PLY byte chunks with backpressure."""
        channel = self.scene_channel
        if not channel or channel.readyState != "open":
            return

        channel.send(json.dumps({
            "type": "splat-stream",
            "format": "ply",
            "bytes": len(self.splat_data),
        }))
        chunks = 0
        for chunk in iter_splat_chunks(self.splat_data):
            while channel.bufferedAmount > 1_000_000:
                await asyncio.sleep(0.01)
            channel.send(chunk)
            chunks += 1
        log.info("splat_stream_sent bytes=%d chunks=%d", len(self.splat_data), chunks)

    async def connect_source(self, source: dict) -> None:
        """Establish the processor's direct recv-only video path to the driver."""
        if self.source_peer:
            await self.source_peer.close()

        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.source_peer = peer
        peer.addTransceiver("video", direction="recvonly")

        @peer.on("track")
        def track(track) -> None:
            if track.kind == "video":
                asyncio.create_task(self.consume(track))

        offer = await peer.createOffer()
        await peer.setLocalDescription(offer)
        await wait_for_ice(peer)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(source["url"], json={
                "purpose": source.get("purpose", "video-source"),
                "offer": {
                    "type": peer.localDescription.type,
                    "sdp": peer.localDescription.sdp,
                },
            })
            response.raise_for_status()
        answer = response.json()
        await peer.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
        log.info("connected_video_source url=%s", source["url"])

    async def consume(self, track) -> None:
        """Continuously consume direct video and send splats after its first frame."""
        while True:
            try:
                await track.recv()
            except Exception:
                self.status({"type": "visual-state", "state": "stale", "frames": self.frames})
                return

            recovered = self.stale_sent
            self.frames += 1
            self.last_frame_at = monotonic()
            self.stale_sent = False
            if self.frames == 1 or recovered:
                self.status({"type": "visual-state", "state": "ready", "frames": self.frames})
            if self.frames == 1:
                await self.send_splats()


pcs: set[RTCPeerConnection] = set()
sessions: set[ProcessorSession] = set()
splat_data: bytes | None = None
stale_task: asyncio.Task | None = None


async def stale_monitor() -> None:
    """Report once when a previously live direct video source becomes stale."""
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
    """Validate the mounted Gaussian scene and close all peers on shutdown."""
    global splat_data, stale_task
    try:
        splat_data = load_splat_ply(SPLAT_FILE)
        log.info("loaded_splats path=%s bytes=%d", SPLAT_FILE, len(splat_data))
    except (OSError, ValueError) as error:
        log.error("splat scene unavailable: %s", error)

    stale_task = asyncio.create_task(stale_monitor())
    yield
    stale_task.cancel()
    await asyncio.gather(*(peer.close() for peer in list(pcs)), return_exceptions=True)


app = FastAPI(title="Ito mock mono processor", lifespan=lifespan)


@app.get("/")
def descriptor() -> dict:
    """Describe the processor's current input and streamed-splat output."""
    return DESCRIPTOR


@app.post("/webrtc")
async def webrtc(request: SignalRequest) -> dict:
    """Create the processor-to-client status and splat-stream session."""
    if request.purpose != "client":
        raise HTTPException(400, "purpose must be client")
    if splat_data is None:
        raise HTTPException(503, f"scene unavailable; mount SPLAT_FILE at {SPLAT_FILE}")

    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    session = ProcessorSession(splat_data)
    pcs.add(peer)
    sessions.add(session)

    @peer.on("connectionstatechange")
    async def changed() -> None:
        log.info("client_peer state=%s", peer.connectionState)
        if peer.connectionState in {"failed", "closed", "disconnected"}:
            sessions.discard(session)
            pcs.discard(peer)
            if session.source_peer:
                await session.source_peer.close()
            await peer.close()

    @peer.on("datachannel")
    def datachannel(channel) -> None:
        if channel.label == "scene":
            session.scene_channel = channel

            @channel.on("message")
            def scene_message(raw) -> None:
                with suppress(ValueError, TypeError):
                    if json.loads(raw).get("type") == "resend-scene":
                        asyncio.create_task(session.send_splats())
        elif channel.label == "status":
            session.status_channel = channel

            @channel.on("message")
            def status_message(raw) -> None:
                with suppress(ValueError, TypeError, KeyError):
                    message = json.loads(raw)
                    if message.get("type") == "video-source":
                        asyncio.create_task(session.connect_source(message))

    await peer.setRemoteDescription(
        RTCSessionDescription(sdp=request.offer.sdp, type=request.offer.type),
    )
    answer = await peer.createAnswer()
    await peer.setLocalDescription(answer)
    await wait_for_ice(peer)
    return {"type": peer.localDescription.type, "sdp": peer.localDescription.sdp}
