"""Macro calendar watcher (CPI, NFP, FOMC, ECB, ...)."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

import yaml

from .router import EventRouter

LOGGER = logging.getLogger(__name__)


class MacroCalendarWatcher:
    """Skeleton watcher that will plug into macro calendar providers."""

    def __init__(self, router: EventRouter, scenarios_path: Path) -> None:
        self.router = router
        self.scenarios_path = scenarios_path
        self.scenarios = self._load_scenarios()
        self._backoff = 120

    def _load_scenarios(self) -> Dict[str, Dict]:
        with self.scenarios_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data.get("scenarios", {})

    async def run(self) -> None:
        while True:
            try:
                await self._refresh()
                self._backoff = 300
            except Exception as exc:  # pragma: no cover - network resilience
                LOGGER.exception("Macro watcher failed: %s", exc)
                self._backoff = min(self._backoff * 2, 900)
            await asyncio.sleep(self._backoff)

    async def _refresh(self) -> None:
        # TODO: Integrate macro calendar provider (e.g. TradingEconomics, FastApi feed)
        LOGGER.debug("Macro watcher placeholder tick; scenarios loaded: %s", list(self.scenarios.keys()))


def create_task(router: EventRouter, scenarios_path: Path) -> asyncio.Task:
    watcher = MacroCalendarWatcher(router=router, scenarios_path=scenarios_path)
    return asyncio.create_task(watcher.run(), name="macro-watcher")
