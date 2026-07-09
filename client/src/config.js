const STORAGE_KEY = "ito.pilotClient.settings.v1";

export const DEFAULT_SETTINGS = Object.freeze({
  serverUrl: defaultServerUrl(),
  requestTimeoutMs: 5000,
  visualFreshnessTimeoutMs: 2000,
  pilotInputRateHz: 60,
  splatBudget: 180,
  splatLifetimeMs: 30000,
});

const SETTING_LIMITS = Object.freeze({
  requestTimeoutMs: [500, 30000],
  visualFreshnessTimeoutMs: [250, 10000],
  pilotInputRateHz: [1, 120],
  splatBudget: [1, 10000],
  splatLifetimeMs: [1000, 300000],
});

export class ClientSettingsStore {
  constructor(storage = globalThis.localStorage) {
    this.storage = storage;
  }

  load() {
    const raw = this.storage?.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    try {
      return normalizeSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(raw) });
    } catch {
      return { ...DEFAULT_SETTINGS };
    }
  }

  save(settings) {
    const normalized = normalizeSettings({ ...DEFAULT_SETTINGS, ...settings });
    this.storage?.setItem(STORAGE_KEY, JSON.stringify(normalized));
    return normalized;
  }

  clear() {
    this.storage?.removeItem(STORAGE_KEY);
  }
}

export function normalizeSettings(settings) {
  const normalized = { ...settings };
  normalized.serverUrl =
    typeof normalized.serverUrl === "string" && normalized.serverUrl.trim()
      ? normalized.serverUrl.trim()
      : DEFAULT_SETTINGS.serverUrl;

  for (const [key, [minimum, maximum]] of Object.entries(SETTING_LIMITS)) {
    normalized[key] = clampInteger(normalized[key], DEFAULT_SETTINGS[key], minimum, maximum);
  }
  return normalized;
}

export function mergeSessionConfig(settings, sessionConfig = {}) {
  return {
    ...sessionConfig,
    pilotInputRateHz: clampInteger(
      sessionConfig.pilotInputRateHz ?? settings.pilotInputRateHz,
      settings.pilotInputRateHz,
      SETTING_LIMITS.pilotInputRateHz[0],
      SETTING_LIMITS.pilotInputRateHz[1],
    ),
    visualFreshnessTimeoutMs: clampInteger(
      sessionConfig.visualFreshnessTimeoutMs ?? settings.visualFreshnessTimeoutMs,
      settings.visualFreshnessTimeoutMs,
      SETTING_LIMITS.visualFreshnessTimeoutMs[0],
      SETTING_LIMITS.visualFreshnessTimeoutMs[1],
    ),
    splatBudget: settings.splatBudget,
    splatLifetimeMs: settings.splatLifetimeMs,
  };
}

function clampInteger(value, fallback, minimum, maximum) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.round(number)));
}

function defaultServerUrl() {
  const location = globalThis.location;
  if (!location?.host) return "ws://localhost:8765";
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.hostname}:8765`;
}
