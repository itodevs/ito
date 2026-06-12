export function processorMatches(driver, processor) {
  return Boolean(driver?.video && processor?.accepts && driver.video.kind === processor.accepts.kind && driver.video.encoding === processor.accepts.encoding && processor?.scene?.format === 'ply');
}

export async function completeIce(pc) {
  if (pc.iceGatheringState === 'complete') return;
  await new Promise(resolve => pc.addEventListener('icegatheringstatechange', () => pc.iceGatheringState === 'complete' && resolve()));
}

export async function signal(pc, url, purpose = 'client') {
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await completeIce(pc);
  const response = await fetch(url, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({purpose, offer: {type: pc.localDescription.type, sdp: pc.localDescription.sdp}})});
  if (!response.ok) throw new Error(`${url}: ${response.status} ${await response.text()}`);
  await pc.setRemoteDescription(await response.json());
}
