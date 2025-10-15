"""On-chain incident watcher (hacks, exploits, whales)."""
from __future__ import annotations

import asyncio
import logging

from .router import EventRouter

LOGGER = logging.getLogger(__name__)


class OnChainWatcher:
    """Polls on-chain intelligence sources."""

    def __init__(self, router: EventRouter) -> None:
        self.router = router
        self._backoff = 90

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
                self._backoff = 180
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("On-chain watcher error: %s", exc)
                self._backoff = min(self._backoff * 2, 900)
            await asyncio.sleep(self._backoff)

    async def _tick(self) -> None:
        # TODO: Connect to on-chain alert sources (e.g., Arkham, EigenPhi)
        LOGGER.debug("On-chain watcher heartbeat")


def create_task(router: EventRouter) -> asyncio.Task:
    watcher = OnChainWatcher(router)
    return asyncio.create_task(watcher.run(), name="onchain-watcher")
