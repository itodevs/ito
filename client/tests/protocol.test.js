import assert from "node:assert/strict";
import test from "node:test";

import { decodeMessagePack, encodeMessagePack } from "../src/msgpack.js";
import { MESSAGE_TYPES, makeEnvelope, packEnvelope, unpackEnvelope } from "../src/protocol.js";

test("MessagePack codec round-trips Ito envelope values", () => {
  const value = {
    protocolVersion: "ito.v1",
    messageId: "message-1",
    type: "catalog.get.result",
    payload: {
      ok: true,
      value: {
        robots: [{ robotId: "droid-1", status: "Available", unavailable: false, score: 1.5 }],
      },
    },
  };

  assert.deepEqual(decodeMessagePack(encodeMessagePack(value)), value);
});

test("Ito envelopes pack and unpack as MessagePack", () => {
  const envelope = makeEnvelope(MESSAGE_TYPES.CATALOG_GET, { includeUnavailable: true }, { messageId: "cat-1" });

  assert.deepEqual(unpackEnvelope(packEnvelope(envelope)), envelope);
});
