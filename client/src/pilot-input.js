const TEXT_ENCODER = new TextEncoder();

export class PilotInputLoop {
  constructor({ transport, rateHz = 60, now = () => performance.now() }) {
    this.transport = transport;
    this.rateHz = rateHz;
    this.now = now;
    this.enabled = false;
    this.sequence = 0;
    this.zeroYawRad = null;
    this.lastSentAt = 0;
  }

  start() {
    this.enabled = true;
    this.sequence = 0;
    this.zeroYawRad = null;
    this.lastSentAt = 0;
  }

  stop() {
    this.enabled = false;
  }

  maybeSend(frame, referenceSpace, sessionId) {
    if (!this.enabled || !this.transport?.canSend()) return null;
    const now = this.now();
    const intervalMs = 1000 / this.rateHz;
    if (now - this.lastSentAt < intervalMs) return null;
    const pose = frame.getViewerPose(referenceSpace);
    if (!pose) return null;
    const snapshot = this.createSnapshot(pose, frame.session.inputSources, sessionId, now);
    this.transport.sendSnapshot(snapshot);
    this.lastSentAt = now;
    return snapshot;
  }

  createSnapshot(viewerPose, inputSources, sessionId, timestampMs = this.now()) {
    const absoluteYaw = yawFromViewerPose(viewerPose);
    if (this.zeroYawRad === null) this.zeroYawRad = absoluteYaw;
    const headsetYawRad = normalizeRadians(absoluteYaw - this.zeroYawRad);
    return {
      protocolVersion: "ito.v1",
      sessionId,
      sequence: ++this.sequence,
      timestampMs: Math.round(timestampMs),
      headsetYawRad,
      controllers: Array.from(inputSources || []).map(controllerSnapshot),
    };
  }
}

export class DataChannelPilotInputTransport {
  constructor(dataChannel = null) {
    this.dataChannel = dataChannel;
  }

  attach(dataChannel) {
    this.dataChannel = dataChannel;
  }

  canSend() {
    return this.dataChannel?.readyState === "open";
  }

  sendSnapshot(snapshot) {
    this.dataChannel.send(TEXT_ENCODER.encode(JSON.stringify(snapshot)));
  }
}

export function yawFromViewerPose(viewerPose) {
  const orientation = viewerPose.transform?.orientation;
  if (orientation) {
    return yawFromQuaternion(orientation.x, orientation.y, orientation.z, orientation.w);
  }
  const matrix = viewerPose.transform?.matrix;
  if (matrix) {
    return Math.atan2(-matrix[8], matrix[10]);
  }
  return 0;
}

function yawFromQuaternion(x, y, z, w) {
  const sinyCosp = 2 * (w * y + z * x);
  const cosyCosp = 1 - 2 * (y * y + x * x);
  return Math.atan2(sinyCosp, cosyCosp);
}

function controllerSnapshot(inputSource) {
  const gamepad = inputSource.gamepad;
  return {
    handedness: inputSource.handedness || "none",
    targetRayMode: inputSource.targetRayMode || "unknown",
    buttons: gamepad
      ? Array.from(gamepad.buttons || []).map((button) => ({
          pressed: Boolean(button.pressed),
          touched: Boolean(button.touched),
          value: Number(button.value || 0),
        }))
      : [],
    axes: gamepad ? Array.from(gamepad.axes || []) : [],
  };
}

function normalizeRadians(value) {
  let normalized = value;
  while (normalized > Math.PI) normalized -= Math.PI * 2;
  while (normalized < -Math.PI) normalized += Math.PI * 2;
  return normalized;
}
