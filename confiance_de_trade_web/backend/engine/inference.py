"""Inference helpers to convert unstructured signals into :class:`RiskEvent`."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..ia.reasoner import ReasonerClient
from .risk import RiskEvent

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class InferenceConfig:
    """Configuration knobs for inference aggregation."""

    default_severity: int = 50
    minimum_relevance_minutes: int = 60


class InferenceEngine:
    """Bridge between external reasoning and the scoring engine."""

    def __init__(
        self,
        reasoner: ReasonerClient,
        config: Optional[InferenceConfig] = None,
        prompt_path: Optional[Path] = None,
    ) -> None:
        self.reasoner = reasoner
        self.config = config or InferenceConfig()
        self.prompt_path = prompt_path or Path(__file__).resolve().parent.parent / "ia" / "classifier_prompt.md"

    async def analyze_social_post(
        self,
        source: str,
        text: str,
        author: str,
        urls: Optional[list[str]] = None,
        severity_hint: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[RiskEvent]:
        """Run an LLM classification on a social update.

        Returns ``None`` when the classifier considers the signal not actionable ``now``.
        """

        payload = {
            "source": source,
            "author": author,
            "text": text,
            "urls": urls or [],
        }
        prompt = self._build_prompt()
        try:
            classification = await self.reasoner.classify_event(prompt, payload)
        except Exception as exc:  # pragma: no cover - defensive logging only
            LOGGER.exception("Classification failed: %s", exc)
            return None

        if not classification:
            return None

        if classification.get("category") == "IRRELEVANT":
            return None

        if not classification.get("is_relevant_now"):
            return None

        immediacy = classification.get("immediacy_minutes")
        if immediacy and immediacy > self.config.minimum_relevance_minutes:
            LOGGER.debug("Drop event due to immediacy %s min > %s", immediacy, self.config.minimum_relevance_minutes)
            return None

        severity = self._compute_severity(classification, severity_hint)
        ts = metadata.get("ts") if metadata else None
        ts = float(ts or time.time())
        meta = {
            "currencies": classification.get("impacted_assets") or [],
            "urgency": classification.get("urgency", 50),
            "credibility": classification.get("credibility", 50),
            "direction_hint": classification.get("direction_hint", "unclear"),
            "explanation": classification.get("explanation"),
            "score_adjustment_points": classification.get("score_adjustment_points", 0),
            "evidence_urls": classification.get("evidence_urls") or [],
            "immediacy_minutes": immediacy,
        }
        if metadata:
            meta.update(metadata)

        event = RiskEvent(
            source=classification.get("source") or source,
            category=classification.get("category"),
            title=text[:160],
            ts=ts,
            severity=severity,
            meta=meta,
        )
        return event

    def _build_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:  # pragma: no cover - defensive fallback
            LOGGER.warning("Classifier prompt file missing at %s", self.prompt_path)
            return "Vous êtes un classifieur JSON."

    def _compute_severity(self, classification: Dict[str, Any], severity_hint: Optional[int]) -> int:
        base = severity_hint if severity_hint is not None else self.config.default_severity
        urgency = float(classification.get("urgency", 50))
        credibility = float(classification.get("credibility", 50))
        adjustment = (urgency - 50) * 0.4 + (credibility - 50) * 0.3
        direction = classification.get("direction_hint")
        if direction == "bearish":
            adjustment += 5
        elif direction == "bullish":
            adjustment -= 5
        severity = max(0, min(100, int(round(base + adjustment))))
        return severity
