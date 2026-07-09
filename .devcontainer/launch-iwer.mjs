import { readFileSync } from "node:fs";
import { chromium } from "playwright";

const profilePath = process.env.IWER_PROFILE_DIR || "/tmp/ito-iwer-profile";
const url = process.argv[2] || "http://host.docker.internal:8080";
const iwerSource = readFileSync("/opt/ito-xr-agent/iwer.min.js", "utf8");

const context = await chromium.launchPersistentContext(profilePath, {
  channel: "chromium",
  headless: true,
  args: [
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=9222",
  ],
});

await context.addInitScript({
  content: `${iwerSource}\nwindow.itoIwerDevice = new IWER.XRDevice(IWER.metaQuest3); window.itoIwerDevice.installRuntime({ forceInstall: true });`,
});
const page = await context.newPage();
await page.goto(url);
console.log(`IWER browser is running at ${url}.`);
console.log("Attach Playwright CLI with: playwright-cli attach --cdp http://127.0.0.1:9222");

await new Promise((resolve) => {
  process.on("SIGINT", resolve);
  process.on("SIGTERM", resolve);
});
await context.close();
