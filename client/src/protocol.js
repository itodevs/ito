import { decodeMessagePack, encodeMessagePack } from "./msgpack.js";

export const PROTOCOL_VERSION = "ito.v1";

export const MESSAGE_TYPES = Object.freeze({
  CONNECTION_HELLO: "connection.hello",
  CONNECTION_HELLO_RESULT: "connection.hello.result",
  CONTROL_START: "control.start",
  CONTROL_START_RESULT: "control.start.result",
  CONTROL_STOP: "control.stop",
  CONTROL_STOP_RESULT: "control.stop.result",
  CONTROL_STOPPED: "control.stopped",
  ROBOT_READY: "robot.ready",
  WEBRTC_OFFER: "webrtc.offer",
  WEBRTC_ANSWER: "webrtc.answer",
});

export const ROLE_PILOT_CLIENT = "pilotClient";

export function makeMessageId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `client-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function makeEnvelope(type, payload = {}, options = {}) {
  const envelope = {
    protocolVersion: PROTOCOL_VERSION,
    messageId: options.messageId || makeMessageId(),
    type,
    payload,
  };
  if (options.replyToMessageId) envelope.replyToMessageId = options.replyToMessageId;
  validateEnvelope(envelope);
  return envelope;
}

export function packEnvelope(envelope) {
  validateEnvelope(envelope);
  return encodeMessagePack(envelope);
}

export function unpackEnvelope(frame) {
  const envelope = decodeMessagePack(frame instanceof ArrayBuffer ? new Uint8Array(frame) : frame);
  validateEnvelope(envelope);
  return envelope;
}

export function validateEnvelope(envelope) {
  if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
    throw new Error("Ito envelope must be a map");
  }
  if (envelope.protocolVersion !== PROTOCOL_VERSION) {
    throw new Error(`unsupported Ito protocol version: ${envelope.protocolVersion}`);
  }
  if (typeof envelope.messageId !== "string" || envelope.messageId.length === 0) {
    throw new Error("Ito envelope requires messageId");
  }
  if (!Object.values(MESSAGE_TYPES).includes(envelope.type)) {
    throw new Error(`unknown Ito message type: ${envelope.type}`);
  }
  if (!envelope.payload || typeof envelope.payload !== "object" || Array.isArray(envelope.payload)) {
    throw new Error("Ito envelope requires payload map");
  }
  if (envelope.replyToMessageId !== undefined && typeof envelope.replyToMessageId !== "string") {
    throw new Error("replyToMessageId must be a string");
  }
  if ("robotId" in envelope || "sessionId" in envelope) {
    throw new Error("robot and session identifiers aren't part of this protocol");
  }
}

export function resultReason(payload) {
  if (!payload || payload.ok !== false) return null;
  return payload.reason || { code: "protocol.invalid_message" };
}

export function displayReason(code, text) {
  const reason = {};
  if (code) reason.code = code;
  if (text) reason.text = text;
  return reason;
}
