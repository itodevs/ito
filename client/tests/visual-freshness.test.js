import assert from "node:assert/strict";
import test from "node:test";

import { VisualFreshnessMonitor } from "../src/visual-freshness.js";

test("visual freshness becomes stale after timeout and fresh again on new batch", () => {
  let time = 0;
  const monitor = new VisualFreshnessMonitor({ timeoutMs: 10, now: () => time });
  let staleEvents = 0;
  let freshEvents = 0;
  monitor.addEventListener("stale", () => {
    staleEvents += 1;
  });
  monitor.addEventListener("fresh", () => {
    freshEvents += 1;
  });

  monitor.markFresh();
  time = 11;
  assert.equal(monitor.tick(), true);
  monitor.markFresh();

  assert.equal(staleEvents, 1);
  assert.equal(freshEvents, 1);
  assert.equal(monitor.stale, false);
});
