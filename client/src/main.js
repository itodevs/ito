import AFRAME from "aframe";

import { ItoPilotApp } from "./app.js";

AFRAME.registerComponent("ito-xr-frame-events", {
  tick() {
    const renderer = this.el.renderer;
    const xr = renderer?.xr;
    if (!xr?.isPresenting) return;
    const frame = xr.getFrame?.();
    const referenceSpace = xr.getReferenceSpace?.();
    if (frame && referenceSpace) {
      this.el.emit("xrframe", { frame, referenceSpace }, false);
    }
  },
});

AFRAME.registerComponent("ito-spark-scene", {
  init() {
    this.batches = [];
  },
  addBatch(batch, entity) {
    this.batches.push({ batch, entity });
  },
});

window.addEventListener("DOMContentLoaded", async () => {
  const app = new ItoPilotApp({
    scene: document.querySelector("a-scene"),
    uiRoot: document.getElementById("ito-ui-root"),
    splatRoot: document.getElementById("ito-splat-root"),
    launchButton: document.getElementById("enter-vr"),
    statusElement: document.getElementById("launch-status"),
  });
  await app.init();
  window.itoPilotApp = app;
});
