export class VisualFreshnessMonitor extends EventTarget {
  constructor({ timeoutMs = 2000, now = () => performance.now() } = {}) {
    super();
    this.timeoutMs = timeoutMs;
    this.now = now;
    this.lastFreshAt = null;
    this.stale = false;
  }

  markFresh() {
    this.lastFreshAt = this.now();
    if (this.stale) {
      this.stale = false;
      this.dispatchEvent(new Event("fresh"));
    }
  }

  reset() {
    this.lastFreshAt = null;
    this.stale = false;
  }

  tick() {
    if (this.lastFreshAt === null || this.stale) return this.stale;
    if (this.now() - this.lastFreshAt >= this.timeoutMs) {
      this.stale = true;
      this.dispatchEvent(new Event("stale"));
    }
    return this.stale;
  }
}
