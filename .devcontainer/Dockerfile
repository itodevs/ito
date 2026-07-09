FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        docker.io \
        docker-compose-v2 \
        git \
        nodejs \
        npm \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN npm install --global @playwright/cli@latest \
    && playwright-cli install-browser chromium --with-deps >/var/log/playwright-browser-install.log 2>&1

RUN PLAYWRIGHT_VERSION=$(node -p "require('/usr/local/lib/node_modules/@playwright/cli/node_modules/playwright/package.json').version") \
    && npm install --prefix /opt/ito-xr-agent "playwright@${PLAYWRIGHT_VERSION}" iwer@2.3.0 \
    && cp /opt/ito-xr-agent/node_modules/iwer/build/iwer.min.js /opt/ito-xr-agent/iwer.min.js

COPY launch-iwer.mjs /opt/ito-xr-agent/launch-iwer.mjs
RUN printf '%s\n' '#!/bin/sh' 'exec node /opt/ito-xr-agent/launch-iwer.mjs "$@"' > /usr/local/bin/ito-iwer \
    && chmod +x /usr/local/bin/ito-iwer

WORKDIR /workspaces/ito
