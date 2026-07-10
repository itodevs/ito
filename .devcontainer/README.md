# Ito Dev Container

Open this repository in a Dev Container, then start the local stack with:

```sh
docker compose up --build
```

The container includes Python, Docker Compose, and `playwright-cli` with its
Chromium browser. To inspect the pilot client from the container:

```sh
playwright-cli open http://host.docker.internal:8080 --browser=chromium
playwright-cli snapshot
```

Use `host.docker.internal` because Docker Compose publishes its ports on the
host while the browser runs inside the Dev Container.

## Agent-driven WebXR emulation

The container includes Meta's Immersive Web Emulation Runtime (IWER). It is
injected before Ito loads, so an agent can drive a simulated Quest 3 without a
headset or a browser extension. Start the agent-controlled browser in one
terminal:

```sh
ito-iwer
```

Then attach the CLI from a second terminal:

```sh
playwright-cli attach --cdp http://127.0.0.1:9222
playwright-cli snapshot
```

IWER exposes the emulated device on `window.itoIwerDevice`, so browser
automation can manipulate its headset pose and controller buttons while
exercising Ito. Use a real headset separately for hardware and platform
integration validation.
