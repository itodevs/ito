import assert from "node:assert/strict";
import test from "node:test";

import { parseSplatBatchHeader } from "../src/splat-scene.js";

test("parseSplatBatchHeader reads Ito v1 binary header", () => {
  const payload = new ArrayBuffer(28);
  const bytes = new Uint8Array(payload);
  bytes.set([73, 84, 79, 83, 80, 76, 65, 84]); // ITOSPLAT
  const view = new DataView(payload);
  view.setUint16(8, 1, true);
  view.setUint16(10, 3, true);
  view.setUint32(12, 9, true);
  view.setUint32(16, 2, true);
  view.setUint16(20, 36, true);

  assert.deepEqual(parseSplatBatchHeader(payload), {
    flags: 3,
    id: "splat-batch-9",
    splatCount: 2,
    recordStride: 36,
  });
});
