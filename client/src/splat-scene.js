export class SplatSceneOwner {
  constructor({ adapter = new NullSplatAdapter(), budget = 180, lifetimeMs = 30000, now = () => performance.now() } = {}) {
    this.adapter = adapter;
    this.budget = budget;
    this.lifetimeMs = lifetimeMs;
    this.now = now;
    this.batches = [];
    this.nextBatchId = 1;
    this.frozen = false;
    this.lastAppliedAt = null;
  }

  setLimits({ budget = this.budget, lifetimeMs = this.lifetimeMs } = {}) {
    this.budget = budget;
    this.lifetimeMs = lifetimeMs;
    this.evict();
  }

  applySplatBatch(payload, metadata = {}) {
    if (this.frozen) return null;
    const batch = {
      id: metadata.id || `splat-batch-${this.nextBatchId++}`,
      payload,
      splatCount: Number.isFinite(metadata.splatCount) ? metadata.splatCount : estimateSplatCount(payload),
      receivedAt: this.now(),
    };
    this.adapter.addBatch(batch);
    this.batches.push(batch);
    this.lastAppliedAt = batch.receivedAt;
    this.evict();
    return batch;
  }

  evict() {
    const cutoff = this.now() - this.lifetimeMs;
    for (const batch of [...this.batches]) {
      if (batch.receivedAt < cutoff) {
        this.removeBatch(batch);
      }
    }
    while (this.totalSplatCount() > this.budget && this.batches.length > 0) {
      this.removeBatch(this.batches[0]);
    }
  }

  setFrozen(frozen) {
    this.frozen = Boolean(frozen);
    this.adapter.setFrozen(this.frozen);
  }

  clear() {
    for (const batch of [...this.batches]) {
      this.removeBatch(batch);
    }
    this.lastAppliedAt = null;
  }

  totalSplatCount() {
    return this.batches.reduce((total, batch) => total + batch.splatCount, 0);
  }

  removeBatch(batch) {
    this.batches = this.batches.filter((candidate) => candidate !== batch);
    this.adapter.removeBatch(batch);
  }
}

export class NullSplatAdapter {
  constructor() {
    this.added = [];
    this.removed = [];
    this.frozen = false;
  }

  addBatch(batch) {
    this.added.push(batch);
  }

  removeBatch(batch) {
    this.removed.push(batch.id);
  }

  setFrozen(frozen) {
    this.frozen = frozen;
  }
}

export class SparkJsSplatAdapter {
  constructor(rootEntity) {
    this.rootEntity = rootEntity;
    this.batchEntities = new Map();
  }

  addBatch(batch) {
    const entity = document.createElement("a-entity");
    entity.setAttribute("data-splat-batch-id", batch.id);
    entity.itoSplatBatch = batch;
    this.rootEntity.appendChild(entity);
    this.batchEntities.set(batch.id, entity);

    if (this.rootEntity.components?.["ito-spark-scene"]?.addBatch) {
      this.rootEntity.components["ito-spark-scene"].addBatch(batch, entity);
    }
  }

  removeBatch(batch) {
    const entity = this.batchEntities.get(batch.id);
    if (entity?.parentNode) entity.parentNode.removeChild(entity);
    this.batchEntities.delete(batch.id);
  }

  setFrozen(frozen) {
    this.rootEntity.setAttribute("data-visual-frozen", frozen ? "true" : "false");
    this.rootEntity.setAttribute("visible", true);
  }
}

export class DataChannelSplatBatchReceiver {
  constructor(sceneOwner) {
    this.sceneOwner = sceneOwner;
  }

  attach(dataChannel) {
    dataChannel.binaryType = "arraybuffer";
    dataChannel.addEventListener("message", (event) => {
      const payload = event.data instanceof ArrayBuffer ? event.data : event.data?.buffer;
      if (payload) this.sceneOwner.applySplatBatch(payload, parseSplatBatchHeader(payload));
    });
  }
}

export function parseSplatBatchHeader(payload) {
  const view =
    payload instanceof ArrayBuffer
      ? new DataView(payload)
      : new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  const magic = String.fromCharCode(...new Uint8Array(view.buffer, view.byteOffset, 8));
  if (magic !== "ITOSPLAT") throw new Error("invalid Ito Splat Batch");
  const version = view.getUint16(8, true);
  if (version !== 1) throw new Error(`unsupported Ito Splat Batch version: ${version}`);
  return {
    flags: view.getUint16(10, true),
    id: `splat-batch-${view.getUint32(12, true)}`,
    splatCount: view.getUint32(16, true),
    recordStride: view.getUint16(20, true),
  };
}

function estimateSplatCount(payload) {
  if (payload?.byteLength) return Math.max(1, Math.floor(payload.byteLength / 32));
  return 1;
}
