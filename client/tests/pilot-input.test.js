import assert from "node:assert/strict";
import test from "node:test";

import { PilotInputLoop } from "../src/pilot-input.js";

test("pilot input snapshots use headset yaw relative to session start", () => {
  let yaw = Math.PI / 4;
  const loop = new PilotInputLoop({ transport: null, now: () => 0 });
  const first = loop.createSnapshot(poseWithYaw(yaw), [], "session-1", 0);

  yaw = Math.PI / 2;
  const second = loop.createSnapshot(poseWithYaw(yaw), [], "session-1", 16);

  assert.equal(first.headsetYawRad, 0);
  assert.ok(Math.abs(second.headsetYawRad - Math.PI / 4) < 0.000001);
  assert.equal(second.sequence, 2);
});

test("pilot input snapshots include controller full state", () => {
  const loop = new PilotInputLoop({ transport: null, now: () => 0 });
  const snapshot = loop.createSnapshot(
    poseWithYaw(0),
    [
      {
        handedness: "right",
        targetRayMode: "tracked-pointer",
        gamepad: {
          buttons: [{ pressed: true, touched: true, value: 1 }],
          axes: [0.1, -0.2],
        },
      },
    ],
    "session-1",
    0,
  );

  assert.deepEqual(snapshot.controllers[0], {
    handedness: "right",
    targetRayMode: "tracked-pointer",
    buttons: [{ pressed: true, touched: true, value: 1 }],
    axes: [0.1, -0.2],
  });
});

function poseWithYaw(yaw) {
  const half = yaw / 2;
  return {
    transform: {
      orientation: {
        x: 0,
        y: Math.sin(half),
        z: 0,
        w: Math.cos(half),
      },
    },
  };
}
