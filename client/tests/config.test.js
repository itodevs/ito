import assert from "node:assert/strict";
import test from "node:test";

import { ClientSettingsStore, DEFAULT_SETTINGS, mergeControlConfig, normalizeSettings } from "../src/config.js";

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }
  getItem(key) {
    return this.values.get(key) || null;
  }
  setItem(key, value) {
    this.values.set(key, value);
  }
  removeItem(key) {
    this.values.delete(key);
  }
}

test("settings fall back to sane defaults", () => {
  const store = new ClientSettingsStore(new MemoryStorage());

  assert.equal(store.load().visualFreshnessTimeoutMs, 2000);
  assert.equal(store.load().pilotInputRateHz, 60);
});

test("settings persist through local storage and clamp unsafe values", () => {
  const store = new ClientSettingsStore(new MemoryStorage());
  const saved = store.save({ ...DEFAULT_SETTINGS, pilotInputRateHz: 1000, splatBudget: -5 });

  assert.equal(saved.pilotInputRateHz, 120);
  assert.equal(saved.splatBudget, 1);
  assert.deepEqual(store.load(), saved);
});

test("control config merges Ito data channel profiles with local client settings", () => {
  const settings = normalizeSettings({ ...DEFAULT_SETTINGS, pilotInputRateHz: 30, splatBudget: 25 });
  const merged = mergeControlConfig(settings, { pilotInputDataChannel: { ordered: false } });

  assert.equal(merged.pilotInputRateHz, 30);
  assert.equal(merged.splatBudget, 25);
  assert.deepEqual(merged.pilotInputDataChannel, { ordered: false });
});
