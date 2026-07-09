import {
  MESSAGE_TYPES,
  ROLE_PILOT_CLIENT,
  displayReason,
  makeEnvelope,
  packEnvelope,
  resultReason,
  unpackEnvelope,
} from "./protocol.js";

export class ItoControlClient extends EventTarget {
  constructor({ serverUrl, requestTimeoutMs = 5000, sessionId = null, WebSocketImpl = globalThis.WebSocket }) {
    super();
    this.serverUrl = serverUrl;
    this.requestTimeoutMs = requestTimeoutMs;
    this.sessionId = sessionId;
    this.WebSocketImpl = WebSocketImpl;
    this.websocket = null;
    this.pending = new Map();
  }

  async connect() {
    if (this.websocket?.readyState === this.WebSocketImpl.OPEN) return;
    this.websocket = new this.WebSocketImpl(this.serverUrl);
    this.websocket.binaryType = "arraybuffer";
    this.websocket.addEventListener("message", (event) => this.handleMessage(event.data));
    this.websocket.addEventListener("close", () => this.dispatchEvent(new Event("closed")));
    this.websocket.addEventListener("error", () => this.dispatchEvent(new Event("error")));

    await new Promise((resolve, reject) => {
      this.websocket.addEventListener("open", resolve, { once: true });
      this.websocket.addEventListener("error", reject, { once: true });
    });

    const payload = { role: ROLE_PILOT_CLIENT };
    if (this.sessionId) payload.sessionId = this.sessionId;
    const hello = await this.request(MESSAGE_TYPES.CONNECTION_HELLO, payload, MESSAGE_TYPES.CONNECTION_HELLO_RESULT);
    if (!hello.ok) throw new DisplayableError(resultReason(hello));
    return hello.value;
  }

  close() {
    this.websocket?.close();
    this.websocket = null;
    for (const pending of this.pending.values()) {
      pending.reject(new DisplayableError(displayReason("connection.closed")));
      clearTimeout(pending.timeoutId);
    }
    this.pending.clear();
  }

  async getCatalog() {
    const result = await this.request(
      MESSAGE_TYPES.CATALOG_GET,
      { includeUnavailable: true },
      MESSAGE_TYPES.CATALOG_GET_RESULT,
    );
    if (!result.ok) throw new DisplayableError(resultReason(result));
    return result.value.robots || [];
  }

  async acquire(robotId) {
    const result = await this.request(
      MESSAGE_TYPES.SESSION_ACQUIRE,
      { robotId },
      MESSAGE_TYPES.SESSION_ACQUIRE_RESULT,
      { robotId },
    );
    if (!result.ok) throw new DisplayableError(resultReason(result));
    this.sessionId = result.value.sessionId;
    return result.value;
  }

  async endSession(sessionId, reason = displayReason("session.ended.pilot_requested"), clean = true) {
    const result = await this.request(
      MESSAGE_TYPES.SESSION_END,
      { reason, clean },
      MESSAGE_TYPES.SESSION_END_RESULT,
      { sessionId },
    );
    if (!result.ok) throw new DisplayableError(resultReason(result));
    return result.value;
  }

  request(type, payload, expectedType, options = {}) {
    const envelope = makeEnvelope(type, payload, {
      robotId: options.robotId,
      sessionId: options.sessionId,
    });
    return new Promise((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        this.pending.delete(envelope.messageId);
        reject(new DisplayableError(displayReason("request.timeout")));
      }, this.requestTimeoutMs);
      this.pending.set(envelope.messageId, { expectedType, resolve, reject, timeoutId });
      this.send(envelope);
    });
  }

  send(envelope) {
    if (!this.websocket || this.websocket.readyState !== this.WebSocketImpl.OPEN) {
      throw new DisplayableError(displayReason("connection.closed"));
    }
    this.websocket.send(packEnvelope(envelope));
  }

  handleMessage(frame) {
    let envelope;
    try {
      envelope = unpackEnvelope(frame);
    } catch (error) {
      this.dispatchEvent(new CustomEvent("protocolerror", { detail: error }));
      return;
    }

    if (envelope.replyToMessageId && this.pending.has(envelope.replyToMessageId)) {
      const pending = this.pending.get(envelope.replyToMessageId);
      this.pending.delete(envelope.replyToMessageId);
      clearTimeout(pending.timeoutId);
      if (pending.expectedType && envelope.type !== pending.expectedType) {
        pending.reject(new DisplayableError(displayReason("protocol.invalid_message")));
      } else {
        pending.resolve(envelope.payload);
      }
      return;
    }

    if (envelope.type === MESSAGE_TYPES.SESSION_ENDED) {
      this.sessionId = null;
      this.dispatchEvent(new CustomEvent("sessionended", { detail: envelope }));
      return;
    }

    this.dispatchEvent(new CustomEvent("message", { detail: envelope }));
  }
}

export class DisplayableError extends Error {
  constructor(reason) {
    super(reason?.text || reason?.code || "Ito request failed");
    this.reason = reason;
  }
}
