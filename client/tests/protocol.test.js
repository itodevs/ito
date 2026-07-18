import assert from "node:assert/strict";
import test from "node:test";

import { MESSAGE_TYPES, makeEnvelope, packEnvelope, unpackEnvelope } from "../src/protocol.js";

test("pilot protocol exposes direct control without catalog or acquisition", () => {
  assert.equal(MESSAGE_TYPES.CONTROL_START, "control.start");
  assert.equal(MESSAGE_TYPES.CONTROL_STOP, "control.stop");
  assert.equal(Object.values(MESSAGE_TYPES).some((type) => type.includes("catalog")), false);
  assert.equal(Object.values(MESSAGE_TYPES).some((type) => type.includes("acquire")), false);
});

test("Ito envelopes have no robot or session identity", () => {
  const envelope = makeEnvelope(MESSAGE_TYPES.CONNECTION_HELLO, { role: "pilotClient" }, { messageId: "hello-1" });

  assert.deepEqual(unpackEnvelope(packEnvelope(envelope)), envelope);
  assert.equal("robotId" in envelope, false);
  assert.equal("sessionId" in envelope, false);
});
