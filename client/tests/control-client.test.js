import assert from "node:assert/strict";
import test from "node:test";

import { ItoControlClient } from "../src/control-client.js";
import { makeEnvelope, packEnvelope } from "../src/protocol.js";

test("control client starts and stops direct control", async () => {
  const requests = [];
  const client = new ItoControlClient({ serverUrl: "ws://ito/ws", WebSocketImpl: class {} });
  client.request = async (...args) => {
    requests.push(args);
    return { ok: true, value: { controlConfig: {} } };
  };

  await client.startControl();
  await client.stopControl();

  assert.deepEqual(requests.map(([type]) => type), ["control.start", "control.stop"]);
  assert.equal(requests.flat().some((value) => value === "catalog.get" || value === "session.acquire"), false);
});

test("control client exposes robot readiness events", () => {
  const client = new ItoControlClient({ serverUrl: "ws://ito/ws", WebSocketImpl: class {} });
  let ready = null;
  client.addEventListener("robotready", (event) => {
    ready = event.detail.payload.ready;
  });

  client.handleMessage(
    packEnvelope(makeEnvelope("robot.ready", { ready: true })),
  );

  assert.equal(ready, true);
});
