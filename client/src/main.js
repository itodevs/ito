import * as THREE from 'three';
import {PLYLoader} from 'three/examples/jsm/loaders/PLYLoader.js';
import {processorMatches, signal} from './protocol.js';
import './style.css';

const DRIVER_URL = '/driver';
const PROCESSOR_URL = '/processor';
const state = {driver: null, processor: null, mode: null, enabled: false, sequence: 0, latestStop: 'none', visual: 'idle', connection: 'setup', lastVideoAt: 0, scene: null, sceneChunks: []};
const summary = document.querySelector('#summary');
const status = document.querySelector('#status');
const enter = document.querySelector('#enter');
const exit = document.querySelector('#exit');
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x051014);
const camera = new THREE.PerspectiveCamera(70, innerWidth / innerHeight, .01, 100); camera.position.set(0, 1.6, 2.4);
const renderer = new THREE.WebGLRenderer({antialias: true}); renderer.setSize(innerWidth, innerHeight); renderer.xr.enabled = true; document.body.append(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xbfffee, 0x182030, 2));
const floor = new THREE.Mesh(new THREE.CircleGeometry(4, 48), new THREE.MeshStandardMaterial({color: 0x0a2828, roughness: 1})); floor.rotation.x = -Math.PI / 2; scene.add(floor);
const interactive = [];

async function discover() {
  const fetchDescriptor = async url => { const response = await fetch(url); if (!response.ok) throw Error(response.status); return response.json(); };
  const [driver, processor] = await Promise.allSettled([fetchDescriptor(DRIVER_URL), fetchDescriptor(PROCESSOR_URL)]);
  state.driver = driver.value; state.processor = processor.value;
  summary.textContent = state.driver ? `${state.driver.name} ready. Enter Ito to choose a view.` : 'Recorded robot is unreachable.';
}
discover();

function block(label, position, color, action) {
  const group = new THREE.Group(); group.position.copy(position);
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(.65, .28, .15), new THREE.MeshStandardMaterial({color, emissive: color, emissiveIntensity: .08})); group.add(mesh);
  const canvas = document.createElement('canvas'); canvas.width = 512; canvas.height = 128; const ctx = canvas.getContext('2d'); ctx.fillStyle = '#eafffa'; ctx.font = 'bold 38px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(label, 256, 78);
  const text = new THREE.Mesh(new THREE.PlaneGeometry(.6, .15), new THREE.MeshBasicMaterial({map: new THREE.CanvasTexture(canvas), transparent: true})); text.position.z = .081; group.add(text); group.userData.action = action; scene.add(group); interactive.push(group); return group;
}
function clearBlocks() { while (interactive.length) scene.remove(interactive.pop()); }
function setupChoices() {
  clearBlocks(); block(state.driver?.name || 'Driver unavailable', new THREE.Vector3(0, 1.55, -1), 0x278d78, showModes);
}
function showModes() {
  clearBlocks(); block('Raw view', new THREE.Vector3(-.45, 1.55, -1), 0x318fb5, () => startSession('raw'));
  if (processorMatches(state.driver, state.processor)) block('Processed PLY', new THREE.Vector3(.45, 1.55, -1), 0x965ad1, () => startSession('processed'));
}
function controls() {
  clearBlocks(); block('ENABLE', new THREE.Vector3(-.35, 1.2, -.8), 0x42d392, () => {state.enabled = true});
  block('STOP', new THREE.Vector3(.35, 1.2, -.8), 0xe35454, () => stopControl('operator-stop'));
}

const tips = [];
for (let i = 0; i < 2; i++) {
  const controller = renderer.xr.getController(i); const tip = new THREE.Mesh(new THREE.SphereGeometry(.025), new THREE.MeshBasicMaterial({color: 0x66ffd7})); controller.add(tip); tips.push({controller, tip, touching: null}); scene.add(controller);
}
function touchButtons() {
  for (const item of tips) {
    const point = new THREE.Vector3(); item.tip.getWorldPosition(point);
    const hit = interactive.find(button => button.worldToLocal(point.clone()).toArray().every((value, index) => Math.abs(value) < [.38, .2, .12][index]));
    if (hit && hit !== item.touching) hit.userData.action();
    item.touching = hit;
  }
}

let driverPc, processorPc, controlChannel, driverStatus, processorStatus, sceneChannel, videoMesh, controlTimer;
function peer() { return new RTCPeerConnection({iceServers: []}); }
function channelOpen(channel) { if (channel.readyState === 'open') return Promise.resolve(); return new Promise((resolve, reject) => { channel.addEventListener('open', resolve, {once:true}); channel.addEventListener('close', () => reject(new Error(`${channel.label} closed before opening`)), {once:true}); }); }
function watchPeer(pc, name) { pc.addEventListener('connectionstatechange', () => {state.connection = `${name}: ${pc.connectionState}`; if (['failed','closed','disconnected'].includes(pc.connectionState)) stopControl(`${name}-disconnect`)}); }
async function startSession(mode) {
  try {
    state.mode = mode; state.connection = 'connecting'; controls(); exit.hidden = false;
    driverPc = peer(); watchPeer(driverPc, 'driver');
    controlChannel = driverPc.createDataChannel('control', {ordered: false, maxRetransmits: 0});
    driverStatus = driverPc.createDataChannel('status'); driverStatus.onmessage = event => handleDriverStatus(JSON.parse(event.data));
    driverPc.ontrack = event => showVideo(event.track);
    driverPc.addTransceiver('video', {direction: mode === 'raw' ? 'recvonly' : 'inactive'});
    await signal(driverPc, `${DRIVER_URL}/webrtc`);
    await channelOpen(driverStatus);
    if (mode === 'processed') await connectProcessor();
    controlTimer = setInterval(sendControl, 1000 / 30);
  } catch (error) { state.connection = `error: ${error.message}`; stopControl('client-error'); }
}
async function connectProcessor() {
  processorPc = peer(); watchPeer(processorPc, 'processor');
  processorStatus = processorPc.createDataChannel('status');
  processorStatus.onmessage = event => { const message = JSON.parse(event.data); if (message.type === 'visual-state') state.visual = message.state; };
  sceneChannel = processorPc.createDataChannel('scene'); sceneChannel.binaryType = 'arraybuffer'; sceneChannel.onmessage = receiveScene;
  await signal(processorPc, `${PROCESSOR_URL}/webrtc`);
  await Promise.all([channelOpen(processorStatus), channelOpen(sceneChannel)]);
  driverStatus.send(JSON.stringify({type: 'request-video-source'}));
}
function handleDriverStatus(message) {
  if (message.type === 'stop-ack') state.latestStop = message.reason;
  if (message.type === 'video-source' && processorStatus?.readyState === 'open') processorStatus.send(JSON.stringify(message));
}
function showVideo(track) {
  const video = document.createElement('video'); video.autoplay = true; video.muted = true; video.playsInline = true; video.srcObject = new MediaStream([track]); video.play();
  const texture = new THREE.VideoTexture(video); videoMesh = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.35), new THREE.MeshBasicMaterial({map: texture})); videoMesh.position.set(0, 1.7, -2); scene.add(videoMesh);
  const updateFreshness = () => { if (video.readyState >= 2) state.lastVideoAt = performance.now(); requestAnimationFrame(updateFreshness); }; updateFreshness();
}
function receiveScene(event) {
  if (typeof event.data === 'string') { state.scene = JSON.parse(event.data); state.sceneChunks = []; return; }
  state.sceneChunks.push(new Uint8Array(event.data));
  if (state.scene && state.sceneChunks.length === state.scene.chunks) {
    const bytes = new Uint8Array(state.scene.bytes); let offset = 0; for (const chunk of state.sceneChunks) {bytes.set(chunk, offset); offset += chunk.length;}
    if (offset !== state.scene.bytes) {sceneChannel.send(JSON.stringify({type: 'resend-scene'})); return;}
    const geometry = new PLYLoader().parse(bytes.buffer); const points = new THREE.Points(geometry, new THREE.PointsMaterial({size: .015, vertexColors: geometry.hasAttribute('color'), color: 0x7fffd4})); points.position.set(0, .3, -1.5); scene.add(points); state.visual = 'ready';
  }
}
function poseOf(object) { const p = new THREE.Vector3(), q = new THREE.Quaternion(); object.getWorldPosition(p); object.getWorldQuaternion(q); return {position: p.toArray(), rotation: q.toArray()}; }
function sendControl() {
  if (!controlChannel || controlChannel.readyState !== 'open' || !renderer.xr.isPresenting) return;
  const message = {type: 'control', sequence: ++state.sequence, sentAtMs: performance.now(), enabled: state.enabled, head: poseOf(camera), controllers: tips.map(({controller}) => poseOf(controller))}; controlChannel.send(JSON.stringify(message));
}
function stopControl(reason) { state.enabled = false; if (controlChannel?.readyState === 'open') controlChannel.send(JSON.stringify({type: 'control', sequence: ++state.sequence, sentAtMs: performance.now(), enabled: false, reason})); }
function closeSession(reason = 'session-exit') { stopControl(reason); clearInterval(controlTimer); driverPc?.close(); processorPc?.close(); state.mode = null; state.visual = 'idle'; state.connection = 'setup'; exit.hidden = true; setupChoices(); }

enter.onclick = async () => { try { const session = await navigator.xr.requestSession('immersive-vr', {optionalFeatures: ['local-floor']}); await renderer.xr.setSession(session); session.addEventListener('end', () => closeSession('xr-exit')); setupChoices(); enter.hidden = true; } catch (error) { summary.textContent = `WebXR unavailable: ${error.message}`; } };
exit.onclick = () => renderer.xr.getSession()?.end();
window.addEventListener('blur', () => stopControl('lost-focus')); window.addEventListener('error', () => stopControl('client-error'));
window.addEventListener('resize', () => {camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight)});
renderer.setAnimationLoop(() => {touchButtons(); if (state.mode === 'raw') state.visual = performance.now() - state.lastVideoAt < 1000 ? 'ready' : 'stale'; status.textContent = `mode: ${state.mode || 'choose in headset'}\nconnection: ${state.connection}\nvisual: ${state.visual}\ncontrol: ${state.enabled ? 'ENABLED' : 'stopped'}\nlatest stop ack: ${state.latestStop}`; renderer.render(scene, camera);});
