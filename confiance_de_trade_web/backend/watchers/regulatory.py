"""Regulatory watcher for SEC/ESMA/ETF developments."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict

import yaml

from .router import EventRouter

LOGGER = logging.getLogger(__name__)


class RegulatoryWatcher:
    """Poll regulatory sources or ingest manual triggers."""

    def __init__(self, router: EventRouter, scenarios_path: Path) -> None:
        self.router = router
        self.scenarios_path = scenarios_path
        self.scenarios = self._load()
        self._backoff = 180

    def _load(self) -> Dict[str, Dict]:
        with self.scenarios_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data.get("scenarios", {})

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
                self._backoff = 600
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Regulatory watcher error: %s", exc)
                self._backoff = min(self._backoff * 2, 1200)
            await asyncio.sleep(self._backoff)

    async def _tick(self) -> None:
        LOGGER.debug("Regulatory watcher idle; scenarios tracked: %s", list(self.scenarios.keys()))


def create_task(router: EventRouter, scenarios_path: Path) -> asyncio.Task:
    watcher = RegulatoryWatcher(router=router, scenarios_path=scenarios_path)
    return asyncio.create_task(watcher.run(), name="regulatory-watcher")
