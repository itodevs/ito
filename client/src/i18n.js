export class TextResources {
  constructor(resources = {}) {
    this.resources = resources;
  }

  static async load(url = "./resources/en/default.json") {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`failed to load text resources: ${response.status}`);
    }
    return new TextResources(await response.json());
  }

  t(key, values = {}) {
    const template = lookup(this.resources, key);
    if (typeof template !== "string") return key;
    return template.replace(/\{\{(\w+)\}\}/g, (_, name) => String(values[name] ?? ""));
  }

  displayReason(reason) {
    if (!reason) return this.t("reason.unknown");
    if (typeof reason === "string") return this.t(reason);
    if (reason.code) {
      const resolved = this.t(reason.code);
      if (resolved !== reason.code) return resolved;
    }
    return reason.text || reason.code || this.t("reason.unknown");
  }

  enumLabel(domain, value) {
    return this.t(`enum.${domain}.${value}`);
  }
}

function lookup(resources, key) {
  return key.split(".").reduce((node, segment) => {
    if (!node || typeof node !== "object") return undefined;
    return node[segment];
  }, resources);
}
