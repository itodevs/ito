import assert from "node:assert/strict";
import test from "node:test";

import { ItoPilotApp } from "../src/app.js";

test("ready screen offers direct control without a robot catalog", () => {
  const buttons = [];
  const app = {
    endpoint: { robotReady: true },
    ui: {
      panel(options) {
        assert.equal(options.title, "Ready");
        return {};
      },
      button(_panel, options) {
        buttons.push(options);
      },
    },
    text: {
      t(key) {
        return {
          "control.ready": "Ready",
          "control.start": "Start control",
          "control.settings": "Settings",
        }[key] || key;
      },
      displayReason() {
        return "";
      },
    },
    resetControl() {},
  };

  ItoPilotApp.prototype.showReady.call(app);

  assert.deepEqual(buttons.map((button) => button.action), ["control.start", "settings.open"]);
});

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

test("controller A/X activation clicks the aimed-at UI action", () => {
  const emitted = [];
  const target = {
    hasAttribute(name) {
      return name === "data-action";
    },
    emit(...args) {
      emitted.push(args);
    },
  };
  const controller = { components: { raycaster: { intersectedEls: [target] } } };

  const activated = ItoPilotApp.prototype.activateControllerTarget.call({}, controller);

  assert.equal(activated, true);
  assert.deepEqual(emitted, [["click", { cursorEl: controller }, true]]);
});

test("controller A/X activation resolves an action from a raycast child mesh", () => {
  const emitted = [];
  const target = {
    emit(...args) {
      emitted.push(args);
    },
  };
  const mesh = {
    closest(selector) {
      assert.equal(selector, "[data-action]");
      return target;
    },
    hasAttribute() {
      return false;
    },
  };
  const controller = { components: { raycaster: { intersectedEls: [mesh] } } };

  const activated = ItoPilotApp.prototype.activateControllerTarget.call({}, controller);

  assert.equal(activated, true);
  assert.deepEqual(emitted, [["click", { cursorEl: controller }, true]]);
});

test("controller A/X activation falls back when no UI action is aimed at", () => {
  const controller = { components: { raycaster: { intersectedEls: [] } } };

  const activated = ItoPilotApp.prototype.activateControllerTarget.call({}, controller);

  assert.equal(activated, false);
});

test("controller handlers are only installed once", () => {
  const originalDocument = globalThis.document;
  const handlers = [];
  globalThis.document = {
    getElementById() {
      return {
        addEventListener(name, callback) {
          handlers.push({ name, callback });
        },
      };
    },
  };
  const app = {
    controllerMenuHandlersInstalled: false,
    activateControllerTarget() {
      return false;
    },
    toggleMenu() {},
  };

  try {
    ItoPilotApp.prototype.installControllerMenuHandlers.call(app);
    ItoPilotApp.prototype.installControllerMenuHandlers.call(app);
  } finally {
    globalThis.document = originalDocument;
  }

  assert.equal(handlers.length, 6);
});
