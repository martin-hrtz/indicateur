"""Generate SESSION_EVENT risk events based on configured sessions."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml
from zoneinfo import ZoneInfo

from ..engine.risk import RiskEvent
from .router import EventRouter

LOGGER = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    name: str
    category: str
    title: str
    weekdays: List[int]
    time: dt_time
    severity: int
    scenario: Optional[str]
    pre_window_minutes: int
    post_window_minutes: int

    @property
    def pre_seconds(self) -> int:
        return self.pre_window_minutes * 60

    @property
    def post_seconds(self) -> int:
        return self.post_window_minutes * 60


class SessionWatcher:
    """Emit session-related planned events."""

    def __init__(self, config_path: Path, router: EventRouter) -> None:
        self.config_path = config_path
        self.router = router
        self._timezone, self.sessions = self._load_config(config_path)
        self._emitted: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _load_config(path: Path) -> tuple[ZoneInfo, List[SessionConfig]]:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        tz_name = data.get("timezone", "Europe/Paris")
        timezone = ZoneInfo(tz_name)
        sessions: List[SessionConfig] = []
        for entry in data.get("sessions", []):
            sessions.append(
                SessionConfig(
                    name=entry["name"],
                    category=entry.get("category", "SESSION_EVENT"),
                    title=entry.get("title", entry["name"]),
                    weekdays=list(entry.get("weekdays", [1, 2, 3, 4, 5])),
                    time=_parse_time(entry.get("time", "08:00")),
                    severity=int(entry.get("severity", 20)),
                    scenario=entry.get("scenario"),
                    pre_window_minutes=int(entry.get("pre_window_minutes", 15)),
                    post_window_minutes=int(entry.get("post_window_minutes", 15)),
                )
            )
        return timezone, sessions

    async def run(self) -> None:
        LOGGER.info("Session watcher started")
        while True:
            try:
                await self._tick()
            except Exception as exc:  # pragma: no cover - resilience
                LOGGER.exception("Session watcher tick failed: %s", exc)
            await asyncio.sleep(30)

    async def _tick(self) -> None:
        now = datetime.now(self._timezone)
        async with self._lock:
            for session in self.sessions:
                for scheduled_dt in self._candidate_datetimes(session, now):
                    if not self._within_window(session, scheduled_dt, now):
                        continue
                    key = f"{session.name}|{scheduled_dt.date().isoformat()}"
                    if key in self._emitted and (now.timestamp() - self._emitted[key]) < 300:
                        continue
                    await self._emit_event(session, scheduled_dt)
                    self._emitted[key] = now.timestamp()

    def _candidate_datetimes(self, session: SessionConfig, now: datetime) -> Iterable[datetime]:
        candidates: List[datetime] = []
        for day_offset in (-1, 0, 1):
            candidate_date = now.date() + timedelta(days=day_offset)
            if candidate_date.isoweekday() not in session.weekdays:
                continue
            dt = datetime.combine(candidate_date, session.time, tzinfo=self._timezone)
            candidates.append(dt)
        return candidates

    @staticmethod
    def _within_window(session: SessionConfig, scheduled_dt: datetime, now: datetime) -> bool:
        delta = scheduled_dt - now
        seconds = delta.total_seconds()
        if seconds > session.pre_seconds:
            return False
        if seconds < -session.post_seconds:
            return False
        return True

    async def _emit_event(self, session: SessionConfig, scheduled_dt: datetime) -> None:
        meta = {
            "timing": "planned",
            "scheduled_ts": scheduled_dt.timestamp(),
            "scenario": session.scenario,
            "pre_window_seconds": session.pre_seconds,
            "post_window_seconds": session.post_seconds,
            "ttl_seconds": session.pre_seconds + session.post_seconds + 900,
        }
        await self.router.emit(
            source="SessionWatcher",
            category=session.category,
            title=session.title,
            severity=session.severity,
            meta=meta,
            ts=scheduled_dt.timestamp(),
        )


def _parse_time(value: str) -> dt_time:
    hour, minute = [int(part) for part in value.split(":", 1)]
    return dt_time(hour=hour, minute=minute)


def create_task(config_path: Path, router: EventRouter) -> asyncio.Task:
    watcher = SessionWatcher(config_path=config_path, router=router)
    return asyncio.create_task(watcher.run(), name="session-watcher")
