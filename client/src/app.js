import { ClientSettingsStore, mergeSessionConfig } from "./config.js";
import { ItoControlClient, DisplayableError } from "./control-client.js";
import { TextResources } from "./i18n.js";
import { DataChannelPilotInputTransport, PilotInputLoop } from "./pilot-input.js";
import { displayReason, ROBOT_STATUS_AVAILABLE } from "./protocol.js";
import { SparkJsSplatAdapter, SplatSceneOwner } from "./splat-scene.js";
import { VisualFreshnessMonitor } from "./visual-freshness.js";
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
    this.catalogRobots = [];
    this.selectedRobot = null;
    this.session = null;
    this.menuOpen = false;
    this.visualPaused = false;
    this.splatScene = null;
    this.freshness = null;
    this.pilotInput = new PilotInputLoop({
      transport: new DataChannelPilotInputTransport(),
      rateHz: this.settings.pilotInputRateHz,
    });
    this.xrReferenceSpace = null;
    this.controllerMenuHandlersInstalled = false;
  }

  async init() {
    this.text = await TextResources.load();
    this.ui = new VrUi(this.uiRoot, this.text);
    this.launchButton.textContent = this.text.t("app.enterVr");
    this.statusElement.textContent = "";
    this.launchButton.addEventListener("click", () => this.enterVr());
    this.scene.addEventListener("click", (event) => this.handleClick(event));
    this.scene.addEventListener("enter-vr", () => this.connectAndShowCatalog());
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

  async connectAndShowCatalog() {
    try {
      this.renderStatus(this.text.t("connection.connecting"));
      this.control = new ItoControlClient({
        serverUrl: this.settings.serverUrl,
        requestTimeoutMs: this.settings.requestTimeoutMs,
      });
      this.control.addEventListener("sessionended", (event) => this.handleSessionEnded(event.detail));
      await this.control.connect();
      await this.showCatalog();
    } catch (error) {
      this.renderStatus(this.reasonText(error));
    }
  }

  async showCatalog(reason = null) {
    this.session = null;
    this.selectedRobot = null;
    this.menuOpen = false;
    this.visualPaused = false;
    this.pilotInput.stop();
    this.splatScene?.clear();
    this.splatScene = null;

    const panel = this.ui.panel({
      title: this.text.t("catalog.title"),
      subtitle: reason ? this.text.displayReason(reason) : "",
    });
    this.ui.button(panel, {
      label: this.text.t("catalog.refresh"),
      position: "1.05 0.82 0.02",
      action: "catalog.refresh",
      width: 0.72,
    });
    this.ui.button(panel, {
      label: this.text.t("session.settings"),
      position: "0.2 0.82 0.02",
      action: "settings.open",
      width: 0.72,
    });

    try {
      this.catalogRobots = await this.control.getCatalog();
      this.renderCatalogRows(panel);
    } catch (error) {
      this.ui.label(panel, this.reasonText(error), "-1.42 0.38 0.02", { color: "#ffd2c9" });
    }
  }

  renderCatalogRows(panel) {
    if (this.catalogRobots.length === 0) {
      this.ui.label(panel, this.text.t("catalog.empty"), "-1.42 0.32 0.02");
      return;
    }
    this.catalogRobots.slice(0, 6).forEach((robot, index) => {
      const y = 0.46 - index * 0.28;
      const type = this.text.enumLabel("robotType", robot.type);
      const status = this.text.enumLabel("robotStatus", robot.status);
      const detail = robot.availabilityDetail ? ` - ${this.text.displayReason(robot.availabilityDetail)}` : "";
      this.ui.label(panel, `${robot.name}  ${type}  ${status}${detail}`, "-1.42 " + y + " 0.02", {
        width: 2.2,
        color: robot.status === ROBOT_STATUS_AVAILABLE ? "#f7fbff" : "#98a7b7",
      });
      this.ui.button(panel, {
        label: robot.status === ROBOT_STATUS_AVAILABLE ? this.text.t("catalog.acquire") : this.text.t("catalog.unavailable"),
        position: `1.02 ${y + 0.02} 0.02`,
        enabled: robot.status === ROBOT_STATUS_AVAILABLE,
        action: "catalog.acquire",
        detail: robot,
        width: 0.72,
      });
    });
  }

  async acquireRobot(robot) {
    this.selectedRobot = robot;
    const panel = this.ui.panel({
      title: this.text.t("connection.connecting"),
      subtitle: this.text.t("session.connecting", { name: robot.name }),
    });
    this.ui.label(panel, this.text.t("connection.connecting"), "-1.42 0.35 0.02");
    try {
      const acquisition = await this.control.acquire(robot.robotId);
      this.startSession(robot, acquisition);
    } catch (error) {
      await this.showCatalog(error.reason);
    }
  }

  startSession(robot, acquisition) {
    const sessionConfig = mergeSessionConfig(this.settings, acquisition.sessionConfig || {});
    this.session = {
      sessionId: acquisition.sessionId,
      robotId: acquisition.robotId,
      robot,
      sessionConfig,
      ended: false,
    };
    this.splatScene = new SplatSceneOwner({
      adapter: new SparkJsSplatAdapter(this.splatRoot),
      budget: sessionConfig.splatBudget,
      lifetimeMs: sessionConfig.splatLifetimeMs,
    });
    this.freshness = new VisualFreshnessMonitor({ timeoutMs: sessionConfig.visualFreshnessTimeoutMs });
    this.freshness.addEventListener("stale", () => this.setVisualPaused(true));
    this.freshness.addEventListener("fresh", () => this.setVisualPaused(false));
    this.freshness.markFresh();
    this.pilotInput.rateHz = sessionConfig.pilotInputRateHz;
    this.pilotInput.start();
    this.renderSession();
  }

  receiveSplatBatch(payload, metadata = {}) {
    if (!this.session || this.session.ended || !this.splatScene) return null;
    if (this.visualPaused) this.freshness?.markFresh();
    const batch = this.splatScene.applySplatBatch(payload, metadata);
    if (batch) this.freshness?.markFresh();
    return batch;
  }

  renderSession() {
    const panel = this.ui.panel({
      title: this.text.t("session.active", { name: this.session.robot.name }),
      subtitle: this.visualPaused ? this.text.t("session.visualPaused") : this.text.t("connection.connected"),
      width: 2.4,
      height: this.menuOpen ? 1.52 : 0.72,
      position: "0 1.85 -2.8",
    });
    this.ui.button(panel, {
      label: this.menuOpen ? this.text.t("session.resume") : this.text.t("session.menu"),
      position: "-0.48 0.0 0.02",
      action: "session.menu.toggle",
      width: 0.82,
    });
    if (this.menuOpen) {
      this.ui.button(panel, {
        label: this.text.t("session.end"),
        position: "0.48 0.0 0.02",
        action: "session.end",
        width: 0.82,
      });
      this.ui.button(panel, {
        label: this.text.t("session.settings"),
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
    if (!paused && !this.menuOpen && !this.session?.ended) this.pilotInput.start();
    if (this.session && !this.session.ended) this.renderSession();
  }

  toggleMenu() {
    if (!this.session?.sessionId || this.session.ended) return;
    this.menuOpen = !this.menuOpen;
    if (this.menuOpen) this.pilotInput.stop();
    if (!this.menuOpen && !this.visualPaused) this.pilotInput.start();
    this.renderSession();
  }

  async endSession() {
    if (!this.session?.sessionId) return;
    this.pilotInput.stop();
    this.ui.panel({ title: this.text.t("session.ending"), subtitle: this.session.robot.name });
    try {
      await this.control.endSession(this.session.sessionId);
    } catch (error) {
      this.handleSessionEnded({
        payload: { reason: error.reason || displayReason("session.ended.requested"), endedBy: "pilotClient", clean: false },
        sessionId: this.session.sessionId,
      });
    }
  }

  handleSessionEnded(envelope) {
    if (!this.session) return;
    this.session.ended = true;
    this.pilotInput.stop();
    this.splatScene?.setFrozen(true);
    const reason = envelope.payload?.reason || displayReason("session.ended.requested");
    const panel = this.ui.panel({
      title: this.text.t("session.ended"),
      subtitle: this.text.displayReason(reason),
      width: 2.8,
      height: 1.35,
      position: "0 1.65 -2.3",
    });
    this.ui.button(panel, {
      label: this.text.t("session.returnToCatalog"),
      position: "0 -0.28 0.02",
      action: "session.returnCatalog",
      width: 1.35,
    });
  }

  showSettings() {
    const panel = this.ui.panel({
      title: this.text.t("settings.title"),
      subtitle: this.settings.serverUrl,
      width: 3.2,
      height: 2.25,
    });
    const rows = [
      ["visualFreshnessTimeoutMs", 250],
      ["pilotInputRateHz", 5],
      ["splatBudget", 20],
      ["splatLifetimeMs", 5000],
    ];
    rows.forEach(([key, step], index) => {
      const y = 0.48 - index * 0.3;
      this.ui.label(panel, `${this.text.t(`settings.${key}`)}: ${this.settings[key]}`, "-1.42 " + y + " 0.02", {
        width: 1.7,
      });
      this.ui.button(panel, { label: "-", position: `0.52 ${y + 0.02} 0.02`, action: "settings.adjust", detail: { key, delta: -step }, width: 0.22 });
      this.ui.button(panel, { label: "+", position: `0.84 ${y + 0.02} 0.02`, action: "settings.adjust", detail: { key, delta: step }, width: 0.22 });
    });
    this.ui.button(panel, {
      label: this.text.t("settings.save"),
      position: "-0.42 -0.82 0.02",
      action: "settings.save",
      width: 0.72,
    });
    this.ui.button(panel, {
      label: this.session ? this.text.t("session.resume") : this.text.t("session.returnToCatalog"),
      position: "0.48 -0.82 0.02",
      action: "settings.close",
      width: 1.05,
    });
  }

  handleClick(event) {
    const target = event.target.closest?.("[data-action]");
    const action = target?.getAttribute("data-action");
    if (!action) return;
    const detail = target.itoActionDetail;
    if (action === "catalog.refresh") this.showCatalog();
    if (action === "catalog.acquire") this.acquireRobot(detail);
    if (action === "session.menu.toggle") this.toggleMenu();
    if (action === "session.end") this.endSession();
    if (action === "session.returnCatalog") this.showCatalog();
    if (action === "settings.open") this.showSettings();
    if (action === "settings.adjust") {
      this.settings[detail.key] += detail.delta;
      this.settings = this.settingsStore.save(this.settings);
      this.showSettings();
    }
    if (action === "settings.save") {
      this.settings = this.settingsStore.save(this.settings);
      if (this.session?.sessionConfig && this.splatScene) {
        this.session.sessionConfig = mergeSessionConfig(this.settings, this.session.sessionConfig);
        this.splatScene.setLimits(this.session.sessionConfig);
      }
      this.showSettings();
    }
    if (action === "settings.close") {
      if (this.session && !this.session.ended) this.renderSession();
      else this.showCatalog();
    }
  }

  onXrFrame({ frame, referenceSpace }) {
    if (!frame || !referenceSpace || !this.session || this.session.ended) return;
    this.xrReferenceSpace = referenceSpace;
    this.freshness?.tick();
    this.splatScene?.evict();
    this.pilotInput.maybeSend(frame, referenceSpace, this.session.sessionId);
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
    this.ui.button(panel, {
      label: this.text.t("catalog.refresh"),
      position: "0 -0.2 0.02",
      action: "catalog.refresh",
      width: 0.85,
    });
  }

  reasonText(error) {
    if (error instanceof DisplayableError) return this.text.displayReason(error.reason);
    return error?.message || this.text.t("reason.unknown");
  }
}
