"""Ito Server application entry point scaffold."""

from __future__ import annotations

import asyncio
import logging

from .config import ServerConfig

LOGGER = logging.getLogger(__name__)


async def run(config: ServerConfig | None = None) -> None:
    """Run the Ito Server scaffold until interrupted.

    WebSocket accept/routing is intentionally implemented in a later TODO item;
    this entry point establishes configuration and container wiring first.
    """

    config = config or ServerConfig.from_env()
    LOGGER.info("Starting Ito Server on %s:%s", config.host, config.port)
    stop = asyncio.Event()
    await stop.wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
