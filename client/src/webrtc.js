import { MESSAGE_TYPES, makeEnvelope } from "./protocol.js";

export const LIVE_PATHS = Object.freeze({
  PILOT_INPUT: "pilotInput",
  CAMERA_MEDIA: "cameraMedia",
  SPLAT_BATCHES: "splatBatches",
});

export async function waitForIceGatheringComplete(peerConnection) {
  if (peerConnection.iceGatheringState === "complete") return;
  await new Promise((resolve) => {
    peerConnection.addEventListener(
      "icegatheringstatechange",
      () => {
        if (peerConnection.iceGatheringState === "complete") resolve();
      },
      { once: false },
    );
  });
}

export async function createNonTrickleOffer(peerConnection) {
  const offer = await peerConnection.createOffer();
  await peerConnection.setLocalDescription(offer);
  await waitForIceGatheringComplete(peerConnection);
  return peerConnection.localDescription.sdp;
}

export async function applyNonTrickleAnswer(peerConnection, sdp) {
  await peerConnection.setRemoteDescription({ type: "answer", sdp });
}

export class PilotInputPeer {
  constructor({ controlClient, dataChannelProfile = {}, RTCPeerConnectionImpl = globalThis.RTCPeerConnection }) {
    this.controlClient = controlClient;
    this.peerConnection = new RTCPeerConnectionImpl({ iceServers: [] });
    this.dataChannel = this.peerConnection.createDataChannel("ito.pilotInput", dataChannelProfile);
  }

  async negotiate() {
    const sdp = await createNonTrickleOffer(this.peerConnection);
    const result = await this.controlClient.request(
      MESSAGE_TYPES.WEBRTC_OFFER,
      { path: LIVE_PATHS.PILOT_INPUT, sdp },
      MESSAGE_TYPES.WEBRTC_ANSWER,
    );
    await applyNonTrickleAnswer(this.peerConnection, result.sdp);
    return this.dataChannel;
  }

  close() {
    this.dataChannel?.close();
    this.peerConnection?.close();
  }
}

export class SplatBatchPeer extends EventTarget {
  constructor({ controlClient, dataChannelProfile = {}, RTCPeerConnectionImpl = globalThis.RTCPeerConnection }) {
    super();
    this.controlClient = controlClient;
    this.peerConnection = new RTCPeerConnectionImpl({ iceServers: [] });
    this.dataChannelProfile = dataChannelProfile;
  }

  async negotiate() {
    this.peerConnection.addEventListener("datachannel", (event) => this.attachDataChannel(event.channel));
    const sdp = await createNonTrickleOffer(this.peerConnection);
    const result = await this.controlClient.request(
      MESSAGE_TYPES.WEBRTC_OFFER,
      { path: LIVE_PATHS.SPLAT_BATCHES, sdp },
      MESSAGE_TYPES.WEBRTC_ANSWER,
    );
    await applyNonTrickleAnswer(this.peerConnection, result.sdp);
  }

  attachDataChannel(dataChannel) {
    dataChannel.binaryType = "arraybuffer";
    dataChannel.addEventListener("message", (event) => {
      const payload = event.data instanceof ArrayBuffer ? event.data : event.data?.buffer;
      if (payload) this.dispatchEvent(new CustomEvent("splatbatch", { detail: payload }));
    });
  }

  close() {
    this.peerConnection?.close();
  }
}
