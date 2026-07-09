import assert from "node:assert/strict";
import test from "node:test";

import { ItoPilotApp } from "../src/app.js";

test("enterVr enters immediately when A-Frame has already loaded", async () => {
  let entered = 0;
  let listenerAdded = false;
  const scene = {
    hasLoaded: true,
    addEventListener() {
      listenerAdded = true;
    },
    enterVR() {
      entered += 1;
    },
  };

  await ItoPilotApp.prototype.enterVr.call({ scene });

  assert.equal(entered, 1);
  assert.equal(listenerAdded, false);
});

test("enterVr waits for A-Frame's loaded event before entering", async () => {
  let resolveLoaded;
  let entered = 0;
  const scene = {
    hasLoaded: false,
    addEventListener(name, callback, options) {
      assert.equal(name, "loaded");
      assert.deepEqual(options, { once: true });
      resolveLoaded = callback;
    },
    enterVR() {
      entered += 1;
    },
  };

  const entering = ItoPilotApp.prototype.enterVr.call({ scene });
  assert.equal(entered, 0);
  resolveLoaded();
  await entering;

  assert.equal(entered, 1);
});
