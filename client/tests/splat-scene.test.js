import assert from "node:assert/strict";
import test from "node:test";

import { NullSplatAdapter, SplatSceneOwner } from "../src/splat-scene.js";

test("splat scene evicts oldest batches over budget", () => {
  let time = 0;
  const adapter = new NullSplatAdapter();
  const scene = new SplatSceneOwner({ adapter, budget: 2, lifetimeMs: 1000, now: () => time });

  scene.applySplatBatch(new Uint8Array(32), { splatCount: 1 });
  time += 1;
  scene.applySplatBatch(new Uint8Array(32), { splatCount: 1 });
  time += 1;
  scene.applySplatBatch(new Uint8Array(32), { splatCount: 1 });

  assert.equal(scene.batches.length, 2);
  assert.deepEqual(adapter.removed, ["splat-batch-1"]);
});

test("splat scene evicts batches past lifetime", () => {
  let time = 0;
  const scene = new SplatSceneOwner({ budget: 10, lifetimeMs: 10, now: () => time });

  scene.applySplatBatch(new Uint8Array(32), { splatCount: 1 });
  time = 11;
  scene.evict();

  assert.equal(scene.batches.length, 0);
});

test("frozen splat scene does not apply new batches", () => {
  const scene = new SplatSceneOwner();

  scene.setFrozen(true);

  assert.equal(scene.applySplatBatch(new Uint8Array(32)), null);
  assert.equal(scene.batches.length, 0);
});
