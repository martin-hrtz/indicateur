"""Microstructure watcher (funding, OI, liquidations)."""
from __future__ import annotations

import asyncio
import logging

from .router import EventRouter

LOGGER = logging.getLogger(__name__)


class MicrostructureWatcher:
    """Track derivatives microstructure anomalies."""

    def __init__(self, router: EventRouter) -> None:
        self.router = router
        self._backoff = 120

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
                self._backoff = 240
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Microstructure watcher error: %s", exc)
                self._backoff = min(self._backoff * 2, 900)
            await asyncio.sleep(self._backoff)

    async def _tick(self) -> None:
        # TODO: Connect to funding/OI/liquidation APIs
        LOGGER.debug("Microstructure watcher idle")


def create_task(router: EventRouter) -> asyncio.Task:
    watcher = MicrostructureWatcher(router)
    return asyncio.create_task(watcher.run(), name="microstructure-watcher")
