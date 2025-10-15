"""Score computation engine for Confiance de Trade."""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from .risk import ActiveContribution, RiskEvent, ScoreState


@dataclass(slots=True)
class CategoryConfig:
    """Runtime representation of category parameters."""

    weight: float
    half_life_seconds: float
    max_age_seconds: float
    timing: str


class ScoreEngine:
    """Maintain CT score based on incoming :class:`RiskEvent` instances."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._config = self._load_config(config_path)
        self._category_configs = self._build_category_config(self._config)
        self._events: Dict[str, RiskEvent] = {}
        self._event_arrival: Dict[str, float] = {}
        self._recent_hashes: Dict[str, float] = {}
        self._active_cache: List[ActiveContribution] = []
        self._baseline: float = float(self._config.get("baseline", 95))
        self._current_score: float = self._baseline
        self._ema_score: float = self._baseline
        self._last_update: float = time.time()
        self._ema_alpha: float = self._compute_alpha(self._config.get("ema", {}))
        clamp_cfg = self._config.get("clamp", {})
        self._clamp_min: float = float(clamp_cfg.get("min_per_second", -5))
        self._clamp_max: float = float(clamp_cfg.get("max_per_second", 3))
        dedup_cfg = self._config.get("deduplication", {})
        self._dedup_window: float = float(dedup_cfg.get("window_seconds", 300))
        self._logistic = self._config.get("logistic", {"mid": 50, "steepness": 0.1, "scale": 100})
        self._timing_rules = self._config.get("timing_rules", {})
        self._asset_multipliers: Dict[str, float] = self._config.get("asset_multipliers", {})
        self._lock = asyncio.Lock()

    @staticmethod
    def _load_config(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    @staticmethod
    def _build_category_config(config: Dict[str, Any]) -> Dict[str, CategoryConfig]:
        result: Dict[str, CategoryConfig] = {}
        for name, values in (config.get("category_defaults") or {}).items():
            result[name] = CategoryConfig(
                weight=float(values.get("weight", 1.0)),
                half_life_seconds=float(values.get("half_life_seconds", config.get("timing_rules", {}).get("breaking", {}).get("default_half_life_seconds", 900))),
                max_age_seconds=float(values.get("max_age_seconds", 3600)),
                timing=str(values.get("timing", "breaking")),
            )
        return result

    @staticmethod
    def _compute_alpha(ema_cfg: Dict[str, Any]) -> float:
        half_life = float(ema_cfg.get("half_life_seconds", 30))
        if half_life <= 0:
            return 1.0
        return 1 - math.exp(-math.log(2) / half_life)

    async def add_event(self, event: RiskEvent) -> bool:
        """Add or update an event, returning ``True`` when accepted."""

        async with self._lock:
            now = time.time()
            key = event.dedup_key()
            last_seen = self._recent_hashes.get(key)
            if last_seen is not None and now - last_seen < self._dedup_window:
                # refresh timestamp but skip duplicate within dedup window
                self._recent_hashes[key] = now
                return False

            self._events[key] = event
            self._event_arrival[key] = now
            self._recent_hashes[key] = now
            self._cleanup_locked(now)
            return True

    async def ingest_events(self, events: Iterable[RiskEvent]) -> None:
        for event in events:
            await self.add_event(event)

    async def tick(self) -> None:
        """Recompute the score using current events."""

        now = time.time()
        async with self._lock:
            self._cleanup_locked(now)
            contributions: List[ActiveContribution] = []
            total_penalty = 0.0
            for key, event in list(self._events.items()):
                penalty, contribution = self._compute_contribution(event, now)
                if penalty <= 1e-6 and contribution.time_weight <= 0:
                    continue
                total_penalty += penalty
                contributions.append(contribution)

            raw_score = max(0.0, min(100.0, self._baseline - total_penalty))
            if math.isnan(self._ema_score):
                self._ema_score = raw_score

            ema_target = raw_score
            ema = self._ema_score + self._ema_alpha * (ema_target - self._ema_score)
            delta = ema - self._current_score
            delta = max(self._clamp_min, min(self._clamp_max, delta))
            self._current_score = max(0.0, min(100.0, self._current_score + delta))
            self._ema_score = ema
            self._active_cache = sorted(contributions, key=lambda c: c.contribution, reverse=True)
            self._last_update = now

    def _cleanup_locked(self, now: float) -> None:
        to_remove: List[str] = []
        for key, event in self._events.items():
            cat_cfg = self._category_configs.get(event.category)
            ttl = float(event.meta.get("ttl_seconds", 0)) or (cat_cfg.max_age_seconds if cat_cfg else 3600)
            if now - event.ts > ttl:
                to_remove.append(key)
        for key in to_remove:
            self._events.pop(key, None)
            self._event_arrival.pop(key, None)

        # prune dedup map
        stale: List[str] = []
        for key, ts in self._recent_hashes.items():
            if now - ts > self._dedup_window:
                stale.append(key)
        for key in stale:
            self._recent_hashes.pop(key, None)

    def _compute_contribution(self, event: RiskEvent, now: float) -> Tuple[float, ActiveContribution]:
        logistic_cfg = self._logistic
        severity = max(0.0, min(100.0, float(event.severity)))
        mid = float(logistic_cfg.get("mid", 50))
        steepness = float(logistic_cfg.get("steepness", 0.1))
        scale = float(logistic_cfg.get("scale", 100))
        logistic_value = 1.0 / (1.0 + math.exp(-steepness * (severity - mid)))
        severity_points = logistic_value * scale

        cat_cfg = self._category_configs.get(event.category)
        weight = cat_cfg.weight if cat_cfg else 1.0
        asset_multiplier = self._asset_multiplier(event)
        time_weight = self._time_weight(event, now, cat_cfg)
        if time_weight <= 0:
            contribution_value = 0.0
        else:
            contribution_value = severity_points * weight * time_weight * asset_multiplier

        urgency = float(event.meta.get("urgency", 50))
        urgency_factor = 0.75 + (urgency / 100) * 0.5
        contribution_value *= urgency_factor

        adjustment = float(event.meta.get("score_adjustment_points", 0.0))
        penalty = contribution_value - adjustment  # subtract bullish adjustment, add bearish

        contribution = ActiveContribution(
            event=event,
            contribution=penalty,
            weight=weight,
            time_weight=time_weight,
            asset_multiplier=asset_multiplier,
        )
        return penalty, contribution

    def _asset_multiplier(self, event: RiskEvent) -> float:
        currencies = event.meta.get("currencies") or []
        if not currencies:
            return float(self._asset_multipliers.get("default", 1.0))
        multipliers = [self._asset_multipliers.get(cur, self._asset_multipliers.get("default", 1.0)) for cur in currencies]
        return max(multipliers) if multipliers else float(self._asset_multipliers.get("default", 1.0))

    def _time_weight(self, event: RiskEvent, now: float, cat_cfg: Optional[CategoryConfig]) -> float:
        scheduled_ts = event.meta.get("scheduled_ts")
        if scheduled_ts:
            return self._planned_time_weight(event, now, cat_cfg, float(scheduled_ts))
        return self._breaking_time_weight(event, now, cat_cfg)

    def _planned_time_weight(
        self, event: RiskEvent, now: float, cat_cfg: Optional[CategoryConfig], scheduled_ts: float
    ) -> float:
        rules = self._timing_rules.get("planned", {})
        category_rules = rules.get("categories", {})
        scenario = event.meta.get("scenario")
        cat_rule = category_rules.get(event.category, {})
        scenario_rule = (cat_rule.get("scenarios") or {}).get(scenario or "", {}) if scenario else {}
        default_rule = rules.get("default", {})

        pre = float(event.meta.get("pre_window_seconds") or scenario_rule.get("pre_seconds") or cat_rule.get("pre_seconds") or default_rule.get("pre_seconds", 0))
        post = float(event.meta.get("post_window_seconds") or scenario_rule.get("post_seconds") or cat_rule.get("post_seconds") or default_rule.get("post_seconds", 0))
        tau = float(event.meta.get("tau_seconds") or scenario_rule.get("tau_seconds") or cat_rule.get("tau_seconds") or default_rule.get("tau_seconds", 1))
        boost = float(event.meta.get("time_boost") or scenario_rule.get("boost") or cat_rule.get("boost") or default_rule.get("boost", 1.0))

        dt = scheduled_ts - now
        if dt > 0 and dt > pre:
            return 0.0
        if dt < 0 and abs(dt) > post:
            return 0.0
        if tau <= 0:
            return boost
        return boost * math.exp(-abs(dt) / tau)

    def _breaking_time_weight(self, event: RiskEvent, now: float, cat_cfg: Optional[CategoryConfig]) -> float:
        half_life = float(event.meta.get("half_life_seconds") or (cat_cfg.half_life_seconds if cat_cfg else self._timing_rules.get("breaking", {}).get("default_half_life_seconds", 900)))
        if half_life <= 0:
            return 1.0
        age = max(0.0, now - event.ts)
        return math.pow(0.5, age / half_life)

    async def get_state(self) -> ScoreState:
        async with self._lock:
            return ScoreState(
                score=round(self._current_score, 2),
                updated_at=self._last_update,
                active=[c.as_dict() for c in self._active_cache],
            )
