import assert from "node:assert/strict";
import test from "node:test";

import { SplatBatchPeer } from "../src/webrtc.js";

class FakePeerConnection extends EventTarget {
  constructor() {
    super();
    this.iceGatheringState = "complete";
    this.localDescription = null;
    this.remoteDescription = null;
  }

  async createOffer() {
    return { type: "offer", sdp: "local offer" };
  }

  async setLocalDescription(description) {
    this.localDescription = description;
  }

  async setRemoteDescription(description) {
    this.remoteDescription = description;
  }

  close() {
    this.closed = true;
  }
}

test("SplatBatchPeer negotiates non-trickle offer over control client", async () => {
  const requests = [];
  const controlClient = {
    request(type, payload, expectedType, options) {
      requests.push({ type, payload, expectedType, options });
      return { sdp: "server answer" };
    },
  };
  const peer = new SplatBatchPeer({
    controlClient,
    sessionId: "session-1",
    RTCPeerConnectionImpl: FakePeerConnection,
  });

  await peer.negotiate();

  assert.equal(requests[0].type, "webrtc.offer");
  assert.equal(requests[0].payload.path, "splatBatches");
  assert.equal(requests[0].payload.sdp, "local offer");
  assert.equal(requests[0].expectedType, "webrtc.answer");
  assert.deepEqual(peer.peerConnection.remoteDescription, { type: "answer", sdp: "server answer" });
});
