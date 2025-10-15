"""Event router bridging watchers and the score engine."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from ..engine.risk import RiskEvent
from ..engine.score import ScoreEngine

LOGGER = logging.getLogger(__name__)


class EventRouter:
    """Thin wrapper that hands watchers' events to the score engine."""

    def __init__(self, engine: ScoreEngine) -> None:
        self.engine = engine

    async def emit(
        self,
        source: str,
        category: str,
        title: str,
        severity: int,
        meta: Dict[str, Any] | None = None,
        ts: float | None = None,
    ) -> bool:
        """Create and forward a :class:`RiskEvent`."""

        event = RiskEvent(
            source=source,
            category=category,
            title=title,
            ts=float(ts or time.time()),
            severity=int(severity),
            meta=meta or {},
        )
        accepted = await self.engine.add_event(event)
        if accepted:
            LOGGER.info("Event accepted %s | %s", source, title)
        else:
            LOGGER.debug("Event deduplicated %s | %s", source, title)
        return accepted
