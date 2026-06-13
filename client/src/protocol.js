/* Small WebRTC and descriptor helpers shared by the browser client. */

// Return whether the selected processor can consume the driver's video and emit splats.
export function processorMatches(driver, processor) {
  return Boolean(
    driver?.video
      && processor?.accepts
      && driver.video.kind === processor.accepts.kind
      && driver.video.encoding === processor.accepts.encoding
      && processor?.scene?.format === 'gaussian-splat-stream',
  );
}

const LOG_PREFIX = '[Ito]';

// Wait for host ICE candidates before sending the one-shot SDP offer.
export async function completeIce(peerConnection) {
  if (peerConnection.iceGatheringState === 'complete') {
    return;
  }

  await new Promise((resolve) => {
    peerConnection.addEventListener('icegatheringstatechange', () => {
      if (peerConnection.iceGatheringState === 'complete') {
        resolve();
      }
    });
  });
}

// Exchange a browser-created offer for a service-created answer.
export async function signal(peerConnection, url, purpose = 'client', configuration = {}) {
  console.info(`${LOG_PREFIX} creating ${purpose} offer`, {url, configuration});
  const offer = await peerConnection.createOffer();
  await peerConnection.setLocalDescription(offer);
  await completeIce(peerConnection);
  console.info(`${LOG_PREFIX} local offer ready`, {
    url,
    purpose,
    signalingState: peerConnection.signalingState,
    sdpLength: peerConnection.localDescription.sdp.length,
  });

  const response = await fetch(url, {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({
      purpose,
      configuration,
      offer: {
        type: peerConnection.localDescription.type,
        sdp: peerConnection.localDescription.sdp,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`${url}: ${response.status} ${await response.text()}`);
  }

  const answer = await response.json();
  console.info(`${LOG_PREFIX} signaling answer received`, {
    url,
    purpose,
    type: answer.type,
    sdpLength: answer.sdp?.length,
  });
  await peerConnection.setRemoteDescription(answer);
}
