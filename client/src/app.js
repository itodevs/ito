import { ClientSettingsStore, mergeControlConfig } from "./config.js";
import { ItoControlClient, DisplayableError } from "./control-client.js";
import { TextResources } from "./i18n.js";
import { DataChannelPilotInputTransport, PilotInputLoop } from "./pilot-input.js";
import { displayReason } from "./protocol.js";
import { SparkJsSplatAdapter, SplatSceneOwner } from "./splat-scene.js";
import { VisualFreshnessMonitor } from "./visual-freshness.js";
import { PilotInputPeer, SplatBatchPeer } from "./webrtc.js";
import { VrUi } from "./vr-ui.js";

export class ItoPilotApp {
  constructor({ scene, uiRoot, splatRoot, launchButton, statusElement }) {
    this.scene = scene;
    this.uiRoot = uiRoot;
    this.splatRoot = splatRoot;
    this.launchButton = launchButton;
    this.statusElement = statusElement;
    this.settingsStore = new ClientSettingsStore();
    this.settings = this.settingsStore.load();
    this.text = new TextResources();
    this.ui = null;
    this.control = null;
    this.endpoint = null;
    this.controlActive = false;
    this.controlConfig = null;
    this.menuOpen = false;
    this.visualPaused = false;
    this.splatScene = null;
    this.freshness = null;
    this.pilotPeer = null;
    this.splatPeer = null;
    this.pilotInput = new PilotInputLoop({
      transport: new DataChannelPilotInputTransport(),
      rateHz: this.settings.pilotInputRateHz,
    });
    this.controllerMenuHandlersInstalled = false;
  }

  async init() {
    this.text = await TextResources.load();
    this.ui = new VrUi(this.uiRoot, this.text);
    this.launchButton.textContent = this.text.t("app.enterVr");
    this.statusElement.textContent = "";
    this.launchButton.addEventListener("click", () => this.enterVr());
    this.scene.addEventListener("click", (event) => this.handleClick(event));
    this.scene.addEventListener("enter-vr", () => this.connectAndShowReady());
    if (this.scene.hasLoaded) this.installControllerMenuHandlers();
    else this.scene.addEventListener("loaded", () => this.installControllerMenuHandlers(), { once: true });
    this.scene.addEventListener("xrframe", (event) => this.onXrFrame(event.detail));

    if (!(await navigator.xr?.isSessionSupported?.("immersive-vr"))) {
      this.statusElement.textContent = this.text.t("app.webxrUnavailable");
      this.launchButton.disabled = true;
    }
  }

  async enterVr() {
    if (!this.scene.hasLoaded) {
      await new Promise((resolve) => this.scene.addEventListener("loaded", resolve, { once: true }));
    }
    this.scene.enterVR();
  }

  async connectAndShowReady() {
    try {
      this.renderStatus(this.text.t("connection.connecting"));
      this.control?.close();
      this.control = new ItoControlClient({
        serverUrl: this.settings.serverUrl,
        requestTimeoutMs: this.settings.requestTimeoutMs,
      });
      this.control.addEventListener("controlstopped", (event) => this.handleControlStopped(event.detail));
      this.control.addEventListener("robotready", (event) => this.handleRobotReady(event.detail));
      this.endpoint = await this.control.connect();
      this.showReady();
    } catch (error) {
      this.renderStatus(this.reasonText(error));
    }
  }

  showReady(reason = null) {
    this.resetControl();
    const panel = this.ui.panel({
      title: this.text.t("control.ready"),
      subtitle: reason ? this.text.displayReason(reason) : "",
    });
    this.ui.button(panel, {
      label: this.endpoint?.robotReady ? this.text.t("control.start") : this.text.t("control.notReady"),
      position: "-0.45 -0.22 0.02",
      enabled: Boolean(this.endpoint?.robotReady),
      action: "control.start",
      width: 1.15,
    });
    this.ui.button(panel, {
      label: this.text.t("control.settings"),
      position: "0.72 -0.22 0.02",
      action: "settings.open",
      width: 0.82,
    });
  }

  handleRobotReady(envelope) {
    if (!this.endpoint || typeof envelope.payload?.ready !== "boolean") return;
    this.endpoint.robotReady = envelope.payload.ready;
    if (!this.controlActive) this.showReady();
  }

  async startControl() {
    this.ui.panel({ title: this.text.t("control.starting") });
    try {
      const result = await this.control.startControl();
      this.controlConfig = mergeControlConfig(this.settings, result.controlConfig || this.endpoint.controlConfig || {});
      this.splatScene = new SplatSceneOwner({
        adapter: new SparkJsSplatAdapter(this.splatRoot),
        budget: this.controlConfig.splatBudget,
        lifetimeMs: this.controlConfig.splatLifetimeMs,
      });
      this.freshness = new VisualFreshnessMonitor({ timeoutMs: this.controlConfig.visualFreshnessTimeoutMs });
      this.freshness.addEventListener("stale", () => this.setVisualPaused(true));
      this.freshness.addEventListener("fresh", () => this.setVisualPaused(false));
      this.pilotPeer = new PilotInputPeer({
        controlClient: this.control,
        dataChannelProfile: this.controlConfig.pilotInputDataChannel,
      });
      this.splatPeer = new SplatBatchPeer({
        controlClient: this.control,
        dataChannelProfile: this.controlConfig.splatBatchDataChannel,
      });
      this.splatPeer.addEventListener("splatbatch", (event) => this.receiveSplatBatch(event.detail));
      const [pilotChannel] = await Promise.all([this.pilotPeer.negotiate(), this.splatPeer.negotiate()]);
      this.pilotInput.transport.attach(pilotChannel);
      this.pilotInput.rateHz = this.controlConfig.pilotInputRateHz;
      this.controlActive = true;
      this.freshness.markFresh();
      this.pilotInput.start();
      this.renderControl();
    } catch (error) {
      try {
        await this.control.stopControl(displayReason("control.stopped.start_failed"));
      } catch {}
      this.showReady(error.reason || displayReason("control.stopped.start_failed", error.message));
    }
  }

  receiveSplatBatch(payload, metadata = {}) {
    if (!this.controlActive || !this.splatScene) return null;
    const batch = this.splatScene.applySplatBatch(payload, metadata);
    if (batch) this.freshness?.markFresh();
    return batch;
  }

  renderControl() {
    const panel = this.ui.panel({
      title: this.text.t("control.active"),
      subtitle: this.visualPaused ? this.text.t("control.visualPaused") : this.text.t("connection.connected"),
      width: 2.4,
      height: this.menuOpen ? 1.52 : 0.72,
      position: "0 1.85 -2.8",
    });
    this.ui.button(panel, {
      label: this.menuOpen ? this.text.t("control.resume") : this.text.t("control.menu"),
      position: "-0.48 0.0 0.02",
      action: "control.menu.toggle",
      width: 0.82,
    });
    if (this.menuOpen) {
      this.ui.button(panel, {
        label: this.text.t("control.stop"),
        position: "0.48 0.0 0.02",
        action: "control.stop",
        width: 0.82,
      });
      this.ui.button(panel, {
        label: this.text.t("control.settings"),
        position: "0 -0.34 0.02",
        action: "settings.open",
        width: 0.92,
      });
    }
  }

  setVisualPaused(paused) {
    this.visualPaused = paused;
    this.splatScene?.setFrozen(paused);
    if (paused) this.pilotInput.stop();
    if (!paused && !this.menuOpen && this.controlActive) this.pilotInput.start();
    if (this.controlActive) this.renderControl();
  }

  toggleMenu() {
    if (!this.controlActive) return;
    this.menuOpen = !this.menuOpen;
    if (this.menuOpen) this.pilotInput.stop();
    if (!this.menuOpen && !this.visualPaused) this.pilotInput.start();
    this.renderControl();
  }

  async stopControl() {
    if (!this.controlActive) return;
    this.pilotInput.stop();
    this.ui.panel({ title: this.text.t("control.stopping") });
    try {
      await this.control.stopControl();
    } catch (error) {
      this.handleControlStopped({ payload: { reason: error.reason || displayReason("control.stopped.pilot_requested") } });
    }
  }

  handleControlStopped(envelope) {
    const reason = envelope.payload?.reason || displayReason("control.stopped.requested");
    this.resetControl();
    const panel = this.ui.panel({
      title: this.text.t("control.stopped"),
      subtitle: this.text.displayReason(reason),
      width: 2.8,
      height: 1.35,
      position: "0 1.65 -2.3",
    });
    this.ui.button(panel, {
      label: this.text.t("control.returnToReady"),
      position: "0 -0.28 0.02",
      action: "control.ready",
      width: 1.35,
    });
  }

  resetControl() {
    this.controlActive = false;
    this.menuOpen = false;
    this.visualPaused = false;
    this.pilotInput?.stop();
    this.pilotPeer?.close();
    this.splatPeer?.close();
    this.pilotPeer = null;
    this.splatPeer = null;
    this.splatScene?.clear();
    this.splatScene = null;
    this.freshness = null;
  }

  showSettings() {
    const panel = this.ui.panel({ title: this.text.t("settings.title"), subtitle: this.settings.serverUrl, width: 3.2, height: 2.25 });
    const rows = [["visualFreshnessTimeoutMs", 250], ["pilotInputRateHz", 5], ["splatBudget", 20], ["splatLifetimeMs", 5000]];
    rows.forEach(([key, step], index) => {
      const y = 0.48 - index * 0.3;
      this.ui.label(panel, `${this.text.t(`settings.${key}`)}: ${this.settings[key]}`, `-1.42 ${y} 0.02`, { width: 1.7 });
      this.ui.button(panel, { label: "-", position: `0.52 ${y + 0.02} 0.02`, action: "settings.adjust", detail: { key, delta: -step }, width: 0.22 });
      this.ui.button(panel, { label: "+", position: `0.84 ${y + 0.02} 0.02`, action: "settings.adjust", detail: { key, delta: step }, width: 0.22 });
    });
    this.ui.button(panel, { label: this.text.t("settings.save"), position: "-0.42 -0.82 0.02", action: "settings.save", width: 0.72 });
    this.ui.button(panel, { label: this.text.t("control.resume"), position: "0.48 -0.82 0.02", action: "settings.close", width: 1.05 });
  }

  handleClick(event) {
    const target = event.target.closest?.("[data-action]");
    const action = target?.getAttribute("data-action");
    if (!action) return;
    const detail = target.itoActionDetail;
    if (action === "connection.retry") this.connectAndShowReady();
    if (action === "control.start") this.startControl();
    if (action === "control.menu.toggle") this.toggleMenu();
    if (action === "control.stop") this.stopControl();
    if (action === "control.ready") this.showReady();
    if (action === "settings.open") this.showSettings();
    if (action === "settings.adjust") {
      this.settings[detail.key] += detail.delta;
      this.settings = this.settingsStore.save(this.settings);
      this.showSettings();
    }
    if (action === "settings.save") {
      this.settings = this.settingsStore.save(this.settings);
      if (this.controlConfig && this.splatScene) {
        this.controlConfig = mergeControlConfig(this.settings, this.controlConfig);
        this.splatScene.setLimits(this.controlConfig);
      }
      this.showSettings();
    }
    if (action === "settings.close") {
      if (this.controlActive) this.renderControl();
      else this.showReady();
    }
  }

  onXrFrame({ frame, referenceSpace }) {
    if (!frame || !referenceSpace || !this.controlActive) return;
    this.freshness?.tick();
    this.splatScene?.evict();
    this.pilotInput.maybeSend(frame, referenceSpace);
  }

  installControllerMenuHandlers() {
    if (this.controllerMenuHandlersInstalled) return;
    this.controllerMenuHandlersInstalled = true;
    for (const id of ["left-controller", "right-controller"]) {
      const controller = document.getElementById(id);
      const activateTargetOrToggleMenu = () => {
        if (!this.activateControllerTarget(controller)) this.toggleMenu();
      };
      controller?.addEventListener("abuttondown", activateTargetOrToggleMenu);
      controller?.addEventListener("xbuttondown", activateTargetOrToggleMenu);
      controller?.addEventListener("menudown", () => this.toggleMenu());
    }
  }

  activateControllerTarget(controller) {
    const target = controller?.components?.raycaster?.intersectedEls
      ?.map((entity) => entity.closest?.("[data-action]") || (entity.hasAttribute("data-action") ? entity : null))
      .find(Boolean);
    if (!target) return false;
    target.emit("click", { cursorEl: controller }, true);
    return true;
  }

  renderStatus(message) {
    const panel = this.ui.panel({ title: message || this.text.t("app.title"), height: 1.0 });
    this.ui.button(panel, { label: this.text.t("connection.retry"), position: "0 -0.2 0.02", action: "connection.retry", width: 0.85 });
  }

  reasonText(error) {
    if (error instanceof DisplayableError) return this.text.displayReason(error.reason);
    return error?.message || this.text.t("reason.unknown");
  }
}
