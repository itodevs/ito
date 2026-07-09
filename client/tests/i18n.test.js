import assert from "node:assert/strict";
import test from "node:test";

import { TextResources } from "../src/i18n.js";

test("text resources resolve nested keys and template values", () => {
  const text = new TextResources({ session: { active: "Piloting {{name}}" } });

  assert.equal(text.t("session.active", { name: "Dory" }), "Piloting Dory");
});

test("display reasons prefer localized resource keys and fall back to free text", () => {
  const text = new TextResources({ reason: { request: { timeout: "Timed out" } } });

  assert.equal(text.displayReason({ code: "reason.request.timeout", text: "Fallback" }), "Timed out");
  assert.equal(text.displayReason({ code: "reason.missing", text: "Fallback" }), "Fallback");
});
