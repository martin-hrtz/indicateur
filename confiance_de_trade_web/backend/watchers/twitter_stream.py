"""Twitter/X streaming watcher feeding the inference engine."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, List

import yaml

from ..engine.inference import InferenceEngine
from .router import EventRouter

LOGGER = logging.getLogger(__name__)


class TwitterStreamWatcher:
    """Consume the Twitter API and forward relevant tweets to the inference engine."""

    def __init__(self, router: EventRouter, inference: InferenceEngine, sources_path: Path) -> None:
        self.router = router
        self.inference = inference
        self.sources_path = sources_path
        self.sources = self._load_sources()
        self.bearer = os.getenv("TWITTER_BEARER")
        self._backoff = 60

    def _load_sources(self) -> Dict[str, List[Dict[str, str]]]:
        with self.sources_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data.get("suggested_accounts", {})

    async def run(self) -> None:
        if not self.bearer:
            LOGGER.warning("Twitter bearer token absent, watcher désactivé")
            return
        while True:
            try:
                await self._stream()
                self._backoff = 60
            except Exception as exc:  # pragma: no cover - external IO
                LOGGER.exception("Twitter stream error: %s", exc)
                self._backoff = min(self._backoff * 2, 600)
            await asyncio.sleep(self._backoff)

    async def _stream(self) -> None:
        # TODO: Plug real Twitter streaming using bearer token.
        LOGGER.debug("Twitter watcher idle; %s accounts configured", sum(len(v) for v in self.sources.values()))

    async def handle_tweet(self, author: str, text: str, urls: List[str] | None = None) -> None:
        event = await self.inference.analyze_social_post(
            source="Twitter",
            text=text,
            author=author,
            urls=urls or [],
            metadata={"timing": "breaking"},
        )
        if event:
            await self.router.emit(
                source=event.source,
                category=event.category,
                title=event.title,
                severity=event.severity,
                meta=event.meta,
                ts=event.ts,
            )


def create_task(router: EventRouter, inference: InferenceEngine, sources_path: Path) -> asyncio.Task:
    watcher = TwitterStreamWatcher(router=router, inference=inference, sources_path=sources_path)
    return asyncio.create_task(watcher.run(), name="twitter-watcher")
