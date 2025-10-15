"""Risk event definitions for Confiance de Trade."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


@dataclass(slots=True)
class RiskEvent:
    """Normalized risk event consumed by the score engine."""

    source: str
    category: str
    title: str
    ts: float
    severity: int
    meta: Dict[str, Any] = field(default_factory=dict)

    def dedup_key(self) -> str:
        """Return a deduplication key combining source and title."""
        return f"{self.source}|{self.title}"


class RiskEventPayload(BaseModel):
    """Pydantic payload for ingestion endpoints."""

    source: str = Field(..., description="Origin of the event, e.g. Twitter, BinanceStatus")
    category: str = Field(..., description="Normalized category name")
    title: str = Field(..., description="Human readable title")
    ts: float = Field(..., description="Epoch timestamp of detection")
    severity: int = Field(..., ge=0, le=100, description="Initial severity 0-100")
    meta: Dict[str, Any] = Field(default_factory=dict)

    @validator("meta", pre=True, always=True)
    def ensure_meta(cls, value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return value or {}

    def to_risk_event(self) -> RiskEvent:
        """Convert the payload to a :class:`RiskEvent`."""
        return RiskEvent(
            source=self.source,
            category=self.category,
            title=self.title,
            ts=self.ts,
            severity=self.severity,
            meta=self.meta,
        )


@dataclass(slots=True)
class ActiveContribution:
    """Computed contribution of an event to the score."""

    event: RiskEvent
    contribution: float
    weight: float
    time_weight: float
    asset_multiplier: float

    def as_dict(self) -> Dict[str, Any]:
        """Serialize contribution for API responses."""
        payload: Dict[str, Any] = {
            "source": self.event.source,
            "category": self.event.category,
            "title": self.event.title,
            "ts": self.event.ts,
            "severity": self.event.severity,
            "meta": self.event.meta,
            "contribution": self.contribution,
            "weight": self.weight,
            "time_weight": self.time_weight,
            "asset_multiplier": self.asset_multiplier,
        }
        return payload


class ScoreState(BaseModel):
    """Serializable score state for websocket and REST responses."""

    score: float
    updated_at: float
    active: List[Dict[str, Any]]
