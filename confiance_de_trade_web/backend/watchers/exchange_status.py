"""Monitor exchange status pages for outages or maintenance."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

import aiohttp

from .router import EventRouter

LOGGER = logging.getLogger(__name__)


class ExchangeStatusWatcher:
    """Polling watcher for centralized exchange status feeds."""

    def __init__(self, router: EventRouter) -> None:
        self.router = router
        self._session: aiohttp.ClientSession | None = None
        self._backoff = 60

    async def run(self) -> None:
        while True:
            try:
                await self._poll()
                self._backoff = 60
            except Exception as exc:  # pragma: no cover - external IO
                LOGGER.exception("Exchange status poll failed: %s", exc)
                self._backoff = min(self._backoff * 2, 600)
            await asyncio.sleep(self._backoff)

    async def _poll(self) -> None:
        if not self._session or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        # TODO: Implement real API polling (Binance, Coinbase...). Placeholder keeps loop alive.
        LOGGER.debug("Exchange status polling placeholder executed")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


def create_task(router: EventRouter) -> asyncio.Task:
    watcher = ExchangeStatusWatcher(router)
    return asyncio.create_task(watcher.run(), name="exchange-status-watcher")
