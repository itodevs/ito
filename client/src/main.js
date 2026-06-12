/*
 * Ito's browser client coordinates direct WebRTC connections while A-Frame
 * owns the WebXR scene and tracked controllers. Spark consumes each incoming
 * PLY byte chunk as a stream and renders its Gaussian splats in that scene.
 */

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

// Fetch the small service descriptors while the user prepares to enter VR.
async function discover() {
  const fetchDescriptor = async (url) => {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`${url}: ${response.status}`);
    }
    return response.json();
  };

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
  showButtonGroup('mode');
  document.querySelector('#processed-choice').setAttribute(
    'visible',
    processorMatches(state.driver, state.processor),
  );
}

// Return a new direct peer connection using local ICE candidates only.
function createPeer() {
  return new RTCPeerConnection({iceServers: []});
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
    state.mode = mode;
    state.connection = 'connecting';
    showButtonGroup('control');
    exit.hidden = false;

    driverPeer = createPeer();
    watchPeer(driverPeer, 'driver');
    controlChannel = driverPeer.createDataChannel('control', {ordered: false, maxRetransmits: 0});
    driverStatusChannel = driverPeer.createDataChannel('status');
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
    state.connection = `error: ${error.message}`;
    stopControl('client-error');
  }
}

// Connect to the processor, then ask the driver how it can subscribe to video.
async function connectProcessor() {
  processorPeer = createPeer();
  watchPeer(processorPeer, 'processor');
  processorStatusChannel = processorPeer.createDataChannel('status');
  processorStatusChannel.addEventListener('message', handleProcessorStatus);
  sceneChannel = processorPeer.createDataChannel('scene');
  sceneChannel.binaryType = 'arraybuffer';
  sceneChannel.addEventListener('message', handleSceneMessage);
  await signal(processorPeer, `${PROCESSOR_URL}/webrtc`);
  await Promise.all([waitForChannel(processorStatusChannel), waitForChannel(sceneChannel)]);
  driverStatusChannel.send(JSON.stringify({type: 'request-video-source'}));
}

// Forward the driver's direct video-source descriptor or display its stop acknowledgement.
function handleDriverStatus(event) {
  const message = JSON.parse(event.data);
  if (message.type === 'video-source' && processorStatusChannel?.readyState === 'open') {
    processorStatusChannel.send(JSON.stringify(message));
  } else if (message.type === 'stop-ack') {
    state.latestStop = message.reason;
  }
}

// Display processor input readiness and freshness reported over status.
function handleProcessorStatus(event) {
  const message = JSON.parse(event.data);
  if (message.type === 'visual-state') {
    state.visual = `processor ${message.state} (${message.frames} frames)`;
    if (message.state === 'ready') {
      state.lastVisualAt = performance.now();
    }
  }
}

// Attach the direct raw-video track to the immersive A-Frame video surface.
function showVideo(event) {
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

// Begin feeding a fresh processor byte stream directly into Spark's PLY decoder.
function beginSplatStream(header) {
  if (state.sceneTransfer) {
    state.sceneTransfer.controller.error(new Error('replaced by a new splat stream'));
    state.sceneTransfer = null;
  }
  if (state.splatMesh) {
    scene.object3D.remove(state.splatMesh);
    state.splatMesh.dispose();
  }

  const stream = new ReadableStream({
    start(controller) {
      state.sceneTransfer = {controller, expected: header.bytes, received: 0};
    },
  });
  const splatMesh = new SplatMesh({
    stream,
    streamLength: header.bytes,
    fileType: 'ply',
    onProgress: (event) => {
      state.visual = `splat stream ${Math.round((event.loaded / header.bytes) * 100)}%`;
    },
    onLoad: () => {
      state.visual = `Gaussian splats ready (${header.bytes} bytes)`;
      state.lastVisualAt = performance.now();
    },
  });
  state.splatMesh = splatMesh;
  scene.object3D.add(splatMesh);
  splatMesh.initialized.catch(() => {
    if (state.splatMesh === splatMesh) {
      requestSceneResend('Spark could not decode the stream');
    }
  });
}

// Feed ordered binary DataChannel chunks into Spark without assembling another PLY copy.
function handleSceneMessage(event) {
  if (typeof event.data === 'string') {
    const header = JSON.parse(event.data);
    if (header.type === 'splat-stream' && header.format === 'ply') {
      beginSplatStream(header);
    }
    return;
  }

  const transfer = state.sceneTransfer;
  if (!transfer) {
    requestSceneResend('chunk arrived before stream header');
    return;
  }

  const chunk = new Uint8Array(event.data);
  transfer.controller.enqueue(chunk);
  transfer.received += chunk.byteLength;
  if (transfer.received === transfer.expected) {
    transfer.controller.close();
    state.sceneTransfer = null;
  } else if (transfer.received > transfer.expected) {
    transfer.controller.error(new Error('splat stream exceeded its declared length'));
    state.sceneTransfer = null;
    requestSceneResend('stream length mismatch');
  }
}

// Ask for a complete replacement stream after a framing or Spark decode failure.
function requestSceneResend(reason) {
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
  sparkRenderer = new SparkRenderer({renderer: scene.renderer});
  scene.object3D.add(sparkRenderer);
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
  await scene.enterVR();
  showButtonGroup('setup');
});
exit.addEventListener('click', () => endSession('operator-exit'));
scene.addEventListener('exit-vr', () => endSession('xr-exit'));
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopControl('lost-focus');
  }
});
window.addEventListener('blur', () => stopControl('lost-focus'));
window.addEventListener('error', () => stopControl('client-error'));

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
    `control: ${state.enabled ? 'ENABLED' : 'stopped'}`,
    `driver stop: ${state.latestStop}`,
  ].join('\n');
}, 250);

discover();
