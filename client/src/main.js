/*
 * Ito's browser client coordinates direct WebRTC connections while A-Frame
 * owns the WebXR scene and tracked controllers. Ordered PLY chunks are collected
 * into the single completed buffer required by the A-Frame-compatible Spark release.
 */

import AFRAME from 'aframe';
import {SparkRenderer, SplatMesh} from '@sparkjsdev/spark';
import {processorMatches, signal} from './protocol.js';

const DRIVER_URL = '/driver';
const PROCESSOR_URL = '/processor';
const STALE_AFTER_MS = 1_000;
const state = {
  driver: null,
  processor: null,
  mode: null,
  enabled: false,
  sequence: 0,
  latestStop: 'none',
  visual: 'idle',
  connection: 'setup',
  lastVisualAt: 0,
  tracking: false,
  sceneTransfer: null,
  splatMesh: null,
  sparkReady: false,
};

const summary = document.querySelector('#summary');
const status = document.querySelector('#status');
const enter = document.querySelector('#enter');
const exit = document.querySelector('#exit');
const video = document.querySelector('#robot-video');
const scene = document.querySelector('a-scene');
const rawSurface = document.querySelector('#raw-surface');
const head = document.querySelector('#head');
const hands = [document.querySelector('#left-hand'), document.querySelector('#right-hand')];
const tips = [...document.querySelectorAll('.touch-tip')];
const buttons = [...document.querySelectorAll('.ito-button')];
let driverPeer;
let processorPeer;
let controlChannel;
let driverStatusChannel;
let processorStatusChannel;
let sceneChannel;
let controlTimer;
let sparkRenderer;

// Prefix browser diagnostics consistently so a copied console log is easy to follow.
function log(message, details) {
  if (details === undefined) {
    console.info(`[Ito] ${message}`);
  } else {
    console.info(`[Ito] ${message}`, details);
  }
}

// Report recoverable failures both in the console and in the visible status panel.
function reportError(context, error) {
  const message = error instanceof Error ? error.message : String(error);
  state.connection = `${context}: ${message}`;
  console.error(`[Ito] ${context}`, error);
}

// Fetch the small service descriptors while the user prepares to enter VR.
async function discover() {
  const fetchDescriptor = async (url) => {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`${url}: ${response.status}`);
    }
    return response.json();
  };

  log('discovering service descriptors', {driver: DRIVER_URL, processor: PROCESSOR_URL});
  const [driver, processor] = await Promise.allSettled([
    fetchDescriptor(DRIVER_URL),
    fetchDescriptor(PROCESSOR_URL),
  ]);
  state.driver = driver.value;
  state.processor = processor.value;
  document.querySelector('#driver-label').setAttribute(
    'value',
    state.driver?.name || 'Driver unavailable',
  );
  log('descriptor discovery complete', {driver, processor});
  summary.textContent = state.driver
    ? `${state.driver.name} ready. Enter Ito to choose a view.`
    : 'Recorded robot is unreachable.';
}

// Toggle groups of physical A-Frame controls without rebuilding the scene.
function showButtonGroup(group) {
  for (const button of buttons) {
    button.setAttribute('visible', button.classList.contains(`${group}-button`));
  }
}

// Present the visual modes compatible with the selected driver.
function showModes() {
  log('driver selected; showing compatible visual modes');
  showButtonGroup('mode');
  document.querySelector('#processed-choice').setAttribute(
    'visible',
    processorMatches(state.driver, state.processor),
  );
}

// Return a new direct peer connection using local ICE candidates only.
function createPeer(name) {
  const peerConnection = new RTCPeerConnection({iceServers: []});
  peerConnection.addEventListener('icecandidate', (event) => {
    log(`${name} ICE candidate`, event.candidate?.candidate || 'gathering complete');
  });
  peerConnection.addEventListener('icecandidateerror', (event) => {
    console.warn(`[Ito] ${name} ICE candidate error`, event);
  });
  return peerConnection;
}

// Log DataChannel lifecycle and buffer state for direct-path diagnosis.
function watchChannel(channel, peerName) {
  for (const eventName of ['open', 'close', 'closing', 'error', 'bufferedamountlow']) {
    channel.addEventListener(eventName, (event) => {
      log(`${peerName} ${channel.label} channel ${eventName}`, {
        readyState: channel.readyState,
        bufferedAmount: channel.bufferedAmount,
        error: event.error,
      });
    });
  }
}

// Resolve after a DataChannel opens, or reject if it closes first.
function waitForChannel(channel) {
  if (channel.readyState === 'open') {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    channel.addEventListener('open', resolve, {once: true});
    channel.addEventListener(
      'close',
      () => reject(new Error(`${channel.label} closed before opening`)),
      {once: true},
    );
  });
}

// Reflect peer state and immediately disable control when a direct path fails.
function watchPeer(peerConnection, name) {
  for (const eventName of ['connectionstatechange', 'iceconnectionstatechange', 'signalingstatechange']) {
    peerConnection.addEventListener(eventName, () => {
      log(`${name} ${eventName}`, {
        connection: peerConnection.connectionState,
        ice: peerConnection.iceConnectionState,
        signaling: peerConnection.signalingState,
      });
    });
  }
  peerConnection.addEventListener('connectionstatechange', () => {
    state.connection = `${name}: ${peerConnection.connectionState}`;
    if (['failed', 'closed', 'disconnected'].includes(peerConnection.connectionState)) {
      stopControl(`${name}-disconnect`);
    }
  });
}

// Start the selected raw-video or processed-splat direct connection path.
async function startSession(mode) {
  try {
    log(`starting ${mode} session`);
    state.mode = mode;
    state.connection = 'connecting';
    showButtonGroup('control');
    exit.hidden = false;

    driverPeer = createPeer('driver');
    watchPeer(driverPeer, 'driver');
    controlChannel = driverPeer.createDataChannel('control', {ordered: false, maxRetransmits: 0});
    driverStatusChannel = driverPeer.createDataChannel('status');
    watchChannel(controlChannel, 'driver');
    watchChannel(driverStatusChannel, 'driver');
    driverStatusChannel.addEventListener('message', handleDriverStatus);
    if (mode === 'raw') {
      driverPeer.addTransceiver('video', {direction: 'recvonly'});
      driverPeer.addEventListener('track', showVideo);
    }
    await signal(driverPeer, `${DRIVER_URL}/webrtc`, 'client', {receiveVideo: mode === 'raw'});
    await waitForChannel(driverStatusChannel);

    if (mode === 'processed') {
      await connectProcessor();
    }
    controlTimer = window.setInterval(sendControl, 1000 / 30);
  } catch (error) {
    reportError('session setup failed', error);
    stopControl('client-error');
  }
}

// Connect to the processor, then ask the driver how it can subscribe to video.
async function connectProcessor() {
  log('connecting processor and preparing scene channel');
  processorPeer = createPeer('processor');
  watchPeer(processorPeer, 'processor');
  processorStatusChannel = processorPeer.createDataChannel('status');
  processorStatusChannel.addEventListener('message', handleProcessorStatus);
  sceneChannel = processorPeer.createDataChannel('scene');
  watchChannel(processorStatusChannel, 'processor');
  watchChannel(sceneChannel, 'processor');
  sceneChannel.binaryType = 'arraybuffer';
  sceneChannel.addEventListener('message', handleSceneMessage);
  await signal(processorPeer, `${PROCESSOR_URL}/webrtc`);
  await Promise.all([waitForChannel(processorStatusChannel), waitForChannel(sceneChannel)]);
  driverStatusChannel.send(JSON.stringify({type: 'request-video-source'}));
}

// Forward the driver's direct video-source descriptor or display its stop acknowledgement.
function handleDriverStatus(event) {
  const message = JSON.parse(event.data);
  log('driver status', message);
  if (message.type === 'video-source' && processorStatusChannel?.readyState === 'open') {
    processorStatusChannel.send(JSON.stringify(message));
  } else if (message.type === 'stop-ack') {
    state.latestStop = message.reason;
  }
}

// Display processor input readiness and freshness reported over status.
function handleProcessorStatus(event) {
  const message = JSON.parse(event.data);
  log('processor status', message);
  if (message.type === 'visual-state') {
    state.visual = `processor ${message.state} (${message.frames} frames)`;
    if (message.state === 'ready') {
      state.lastVisualAt = performance.now();
    }
  }
}

// Attach the direct raw-video track to the immersive A-Frame video surface.
function showVideo(event) {
  log('received raw video track', {kind: event.track.kind, id: event.track.id});
  video.srcObject = new MediaStream([event.track]);
  video.play().catch(() => {
    state.visual = 'raw video waiting for playback';
  });
  rawSurface.setAttribute('visible', true);
  state.visual = 'raw video ready';
  state.lastVisualAt = performance.now();

  const markFrame = () => {
    state.lastVisualAt = performance.now();
    video.requestVideoFrameCallback(markFrame);
  };
  if ('requestVideoFrameCallback' in video) {
    video.requestVideoFrameCallback(markFrame);
  } else {
    video.addEventListener('timeupdate', () => {
      state.lastVisualAt = performance.now();
    });
  }
}

// Allocate the complete PLY buffer expected by the A-Frame-compatible Spark release.
function beginSplatTransfer(header) {
  if (!state.sparkReady) {
    requestSceneResend('Spark renderer is not ready');
    return;
  }

  try {
    if (header.bytes > 1_000_000_000) {
      console.warn('[Ito] very large splat scene may exceed browser memory', header);
    }
    state.sceneTransfer = {
      bytes: new Uint8Array(header.bytes),
      expected: header.bytes,
      received: 0,
      chunks: 0,
    };
    state.visual = `receiving Gaussian splats (0 / ${header.bytes} bytes)`;
    log('splat transfer started', header);
  } catch (error) {
    reportError(`could not allocate ${header.bytes} bytes for the splat scene`, error);
  }
}

// Append ordered DataChannel chunks, then hand the completed PLY bytes to Spark.
function handleSceneMessage(event) {
  if (typeof event.data === 'string') {
    const header = JSON.parse(event.data);
    log('scene channel message', header);
    if (header.type === 'splat-stream' && header.format === 'ply') {
      beginSplatTransfer(header);
    }
    return;
  }

  const transfer = state.sceneTransfer;
  if (!transfer) {
    requestSceneResend('chunk arrived before stream header');
    return;
  }

  const chunk = new Uint8Array(event.data);
  if (transfer.received + chunk.byteLength > transfer.expected) {
    state.sceneTransfer = null;
    requestSceneResend('stream length mismatch');
    return;
  }

  transfer.bytes.set(chunk, transfer.received);
  transfer.received += chunk.byteLength;
  transfer.chunks += 1;
  if (transfer.chunks === 1 || transfer.chunks % 1000 === 0) {
    log('splat transfer progress', {received: transfer.received, expected: transfer.expected});
  }
  state.visual = `receiving Gaussian splats (${transfer.received} / ${transfer.expected} bytes)`;

  if (transfer.received === transfer.expected) {
    state.sceneTransfer = null;
    showSplats(transfer.bytes);
  }
}

// Replace the current scene with a Spark mesh decoded by the shared A-Frame Three.js runtime.
function showSplats(fileBytes) {
  if (state.splatMesh) {
    scene.object3D.remove(state.splatMesh);
    state.splatMesh.dispose();
  }

  log('handing completed PLY to Spark', {bytes: fileBytes.byteLength});
  const splatMesh = new SplatMesh({
    fileBytes,
    fileType: 'ply',
    onLoad: () => {
      state.visual = `Gaussian splats ready (${fileBytes.byteLength} bytes)`;
      state.lastVisualAt = performance.now();
      log('Spark loaded Gaussian splats', {splats: splatMesh.numSplats});
    },
  });
  state.splatMesh = splatMesh;
  scene.object3D.add(splatMesh);
  splatMesh.initialized.catch((error) => {
    reportError('Spark could not decode the PLY', error);
    if (state.splatMesh === splatMesh) {
      requestSceneResend('Spark could not decode the PLY');
    }
  });
}

// Ask for a complete replacement stream after a framing or Spark decode failure.
function requestSceneResend(reason) {
  console.warn('[Ito] requesting complete scene resend', reason);
  state.visual = `requesting splat resend: ${reason}`;
  if (sceneChannel?.readyState === 'open') {
    sceneChannel.send(JSON.stringify({type: 'resend-scene'}));
  }
}

// Convert an A-Frame tracked object into the small right-handed pose message.
function poseOf(entity) {
  const position = new AFRAME.THREE.Vector3();
  const rotation = new AFRAME.THREE.Quaternion();
  entity.object3D.getWorldPosition(position);
  entity.object3D.getWorldQuaternion(rotation);
  return {
    position: position.toArray(),
    rotation: rotation.toArray(),
  };
}

// Send the newest tracked poses; unreliable delivery intentionally drops old commands.
function sendControl() {
  if (!controlChannel || controlChannel.readyState !== 'open') {
    return;
  }
  if (!state.tracking && state.enabled) {
    stopControl('lost-tracking');
  }

  controlChannel.send(JSON.stringify({
    type: 'control',
    sequence: ++state.sequence,
    sentAtMs: performance.now(),
    enabled: state.enabled,
    head: poseOf(head),
    left: hands[0].components['tracked-controls'] ? poseOf(hands[0]) : undefined,
    right: hands[1].components['tracked-controls'] ? poseOf(hands[1]) : undefined,
  }));
}

// Disable locally first, then send one explicit disabled command when possible.
function stopControl(reason) {
  state.enabled = false;
  if (controlChannel?.readyState === 'open') {
    controlChannel.send(JSON.stringify({
      type: 'control',
      sequence: ++state.sequence,
      sentAtMs: performance.now(),
      enabled: false,
      reason,
      head: poseOf(head),
    }));
  }
}

// Close every direct path and return the immersive scene to its setup choices.
function endSession(reason = 'session-ended') {
  log('ending session', reason);
  stopControl(reason);
  window.clearInterval(controlTimer);
  driverPeer?.close();
  processorPeer?.close();
  driverPeer = undefined;
  processorPeer = undefined;
  rawSurface.setAttribute('visible', false);
  if (state.splatMesh) {
    scene.object3D.remove(state.splatMesh);
    state.splatMesh.dispose();
    state.splatMesh = null;
  }
  exit.hidden = true;
  state.mode = null;
  state.connection = 'setup';
  showButtonGroup('setup');
}

// Fire a block action once per controller contact instead of once per frame.
function touchButtons(component) {
  for (const tip of tips) {
    const point = new AFRAME.THREE.Vector3();
    tip.object3D.getWorldPosition(point);
    const hit = buttons.find((button) => {
      if (!button.object3D.visible) {
        return false;
      }
      const local = button.object3D.worldToLocal(point.clone());
      return Math.abs(local.x) < 0.38 && Math.abs(local.y) < 0.2 && Math.abs(local.z) < 0.12;
    });
    if (hit && hit !== component.touching.get(tip)) {
      hit.emit('ito-touch');
    }
    component.touching.set(tip, hit);
  }
}

// Register the small per-frame bridge from A-Frame tracking to Ito interaction state.
AFRAME.registerComponent('ito-app', {
  init() {
    log('Ito A-Frame component initialized', {threeRevision: AFRAME.THREE.REVISION});
    this.touching = new Map();
  },

  tick() {
    state.tracking = Boolean(this.el.renderer?.xr.getFrame());
    touchButtons(this);
  },
});
scene.setAttribute('ito-app', '');

// Install Spark beside A-Frame's objects once its WebGL renderer exists.
scene.addEventListener('renderstart', () => {
  try {
    log('A-Frame render started', {
      threeRevision: AFRAME.THREE.REVISION,
      webgl2: scene.renderer.capabilities.isWebGL2,
    });
    sparkRenderer = new SparkRenderer({renderer: scene.renderer});
    scene.object3D.add(sparkRenderer);
    state.sparkReady = true;
    log('Spark renderer initialized with A-Frame renderer');
  } catch (error) {
    reportError('Spark renderer initialization failed', error);
  }
});

// Wire the static A-Frame blocks to direct actions.
document.querySelector('#driver-choice').addEventListener('ito-touch', showModes);
document.querySelector('#raw-choice').addEventListener('ito-touch', () => startSession('raw'));
document.querySelector('#processed-choice').addEventListener('ito-touch', () => startSession('processed'));
document.querySelector('#enable-control').addEventListener('ito-touch', () => {
  state.enabled = true;
});
document.querySelector('#stop-control').addEventListener('ito-touch', () => stopControl('operator-stop'));

// Keep the browser-required user gesture obvious and available immediately.
enter.addEventListener('click', async () => {
  log('Enter Ito clicked', {isSecureContext, xrAvailable: Boolean(navigator.xr)});
  try {
    await scene.enterVR();
    showButtonGroup('setup');
  } catch (error) {
    reportError('could not enter VR', error);
  }
});
exit.addEventListener('click', () => endSession('operator-exit'));
scene.addEventListener('enter-vr', () => log('entered VR'));
scene.addEventListener('exit-vr', () => {
  log('exited VR');
  endSession('xr-exit');
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopControl('lost-focus');
  }
});
window.addEventListener('blur', () => stopControl('lost-focus'));
window.addEventListener('error', (event) => {
  console.error('[Ito] uncaught browser error', event.error || event.message);
  stopControl('client-error');
});
window.addEventListener('unhandledrejection', (event) => {
  console.error('[Ito] unhandled promise rejection', event.reason);
  stopControl('client-error');
});

// Render concise debug state independently from network callbacks.
window.setInterval(() => {
  const stale = state.mode === 'raw'
    ? state.lastVisualAt && performance.now() - state.lastVisualAt > STALE_AFTER_MS
    : state.visual.includes('stale');
  status.classList.toggle('stale', Boolean(stale));
  status.textContent = [
    `mode: ${state.mode || 'none'}`,
    `connection: ${state.connection}`,
    `visual: ${state.visual}${stale ? ' (stale)' : ''}`,
    `tracking: ${state.tracking ? 'tracked' : 'not tracked'}`,
    `spark: ${state.sparkReady ? 'ready' : 'not ready'}`,
    `control: ${state.enabled ? 'ENABLED' : 'stopped'}`,
    `driver stop: ${state.latestStop}`,
  ].join('\n');
}, 250);

log('client module loaded', {
  aframe: AFRAME.version,
  threeRevision: AFRAME.THREE.REVISION,
  secureContext: isSecureContext,
  xrAvailable: Boolean(navigator.xr),
});
discover();
