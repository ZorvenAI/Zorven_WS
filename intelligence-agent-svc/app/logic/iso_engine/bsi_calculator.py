"""
Brand Strength Index (BSI) calculator — ISO 10668 multi-pillar scoring.

BSI is scored 0–100 across three pillars:
  - Financial (40%): Revenue growth, margins, market share
  - Behavioral (35%): Awareness, sentiment, loyalty
  - Legal (25%): Trademark strength, geographic coverage

When data for a pillar is missing, the ProxyEngine redistributes
weights across available pillars (normalized to sum to 1.0).
"""

import logging
from typing import Any

from app.api.schemas import BSIResult, PillarScore
from app.logic.iso_engine.proxy_engine import ProxyEngine

logger = logging.getLogger(__name__)

# Default pillar weights (when all data available)
DEFAULT_WEIGHTS: dict[str, float] = {
    "financial": 0.40,
    "behavioral": 0.35,
    "legal": 0.25,
}

# Stub scores when real data is unavailable
STUB_SCORES: dict[str, float] = {
    "financial": 65.0,
    "behavioral": 60.0,
    "legal": 70.0,
}


class BSICalculator:
    """Brand Strength Index — ISO 10668 multi-pillar scoring."""

    def __init__(self, proxy_engine: ProxyEngine | None = None) -> None:
        self.proxy_engine = proxy_engine or ProxyEngine()

    def derive_index(
        self,
        financial_data: dict[str, Any] | None = None,
        behavioral_data: dict[str, Any] | None = None,
        legal_data: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
    ) -> BSIResult:
        """
        Calculate BSI from available pillar data.

        Args:
            financial_data: Revenue growth, margins, market share metrics.
            behavioral_data: Awareness, sentiment, loyalty metrics.
            legal_data: Trademark, geographic coverage metrics.
            weights: Custom pillar weights (default: 40/35/25).

        Returns:
            BSIResult with overall score, per-pillar breakdown, and data completeness.
        """
        base_weights = weights or DEFAULT_WEIGHTS

        # Determine which pillars have data
        pillar_data = {
            "financial": financial_data,
            "behavioral": behavioral_data,
            "legal": legal_data,
        }
        available_pillars = [
            name for name, data in pillar_data.items() if data is not None
        ]
        total_pillars = len(DEFAULT_WEIGHTS)
        data_completeness = len(available_pillars) / total_pillars

        # Redistribute weights for available pillars
        if len(available_pillars) < total_pillars and len(available_pillars) > 0:
            effective_weights = self.proxy_engine.redistribute_weights(
                available_pillars, base_weights
            )
            logger.info(
                "BSI: %d/%d pillars available, redistributed weights: %s",
                len(available_pillars),
                total_pillars,
                effective_weights,
            )
        elif len(available_pillars) == 0:
            # No data at all — use stub scores with default weights
            effective_weights = base_weights
            available_pillars = list(DEFAULT_WEIGHTS.keys())
            pillar_data = {name: {} for name in available_pillars}
            data_completeness = 0.0
            logger.warning("BSI: No pillar data available, using stub scores")
        else:
            effective_weights = base_weights

        # Score each pillar
        pillar_scores: list[PillarScore] = []
        weighted_sum = 0.0

        for pillar_name in available_pillars:
            data = pillar_data.get(pillar_name)
            weight = effective_weights.get(pillar_name, 0.0)
            score = self._score_pillar(pillar_name, data)
            rationale = self._pillar_rationale(pillar_name, data, score)

            pillar_scores.append(
                PillarScore(
                    name=pillar_name,
                    weight=round(weight, 4),
                    score=round(score, 1),
                    rationale=rationale,
                )
            )
            weighted_sum += score * weight

        overall_score = int(round(weighted_sum))
        overall_score = max(0, min(100, overall_score))

        logger.info(
            "BSI score: %d/100 (completeness: %.0f%%)",
            overall_score,
            data_completeness * 100,
        )

        return BSIResult(
            score=overall_score,
            pillars=pillar_scores,
            data_completeness=round(data_completeness, 2),
        )

    def _score_pillar(self, pillar_name: str, data: dict[str, Any] | None) -> float:
        """Score a single pillar (0–100)."""
        if not data:
            return STUB_SCORES.get(pillar_name, 50.0)

        # Check if data contains a pre-computed score
        if "score" in data:
            return float(data["score"])

        # Financial pillar scoring
        if pillar_name == "financial":
            return self._score_financial(data)

        # Behavioral pillar scoring
        if pillar_name == "behavioral":
            return self._score_behavioral(data)

        # Legal pillar scoring
        if pillar_name == "legal":
            return self._score_legal(data)

        return STUB_SCORES.get(pillar_name, 50.0)

    @staticmethod
    def _score_financial(data: dict[str, Any]) -> float:
        """Score financial pillar from metrics."""
        score = 50.0  # Base score
        growth = data.get("revenue_growth")
        if growth is not None:
            # >10% growth = 80+, 5-10% = 60-80, <5% = 40-60
            score = min(100, max(0, 40 + float(growth) * 400))
        margin = data.get("profit_margin")
        if margin is not None:
            margin_score = min(100, max(0, float(margin) * 200))
            score = (score + margin_score) / 2
        market_share = data.get("market_share")
        if market_share is not None:
            share_score = min(100, max(0, float(market_share) * 300))
            score = (score * 2 + share_score) / 3
        return score

    @staticmethod
    def _score_behavioral(data: dict[str, Any]) -> float:
        """Score behavioral pillar from metrics."""
        score = 50.0
        awareness = data.get("brand_awareness")
        if awareness is not None:
            score = float(awareness)  # Assume 0-100 scale
        sentiment = data.get("sentiment_score")
        if sentiment is not None:
            sent_score = float(sentiment)
            score = (score + sent_score) / 2
        loyalty = data.get("customer_loyalty")
        if loyalty is not None:
            loyalty_score = float(loyalty)
            score = (score * 2 + loyalty_score) / 3
        return max(0, min(100, score))

    @staticmethod
    def _score_legal(data: dict[str, Any]) -> float:
        """Score legal pillar from metrics."""
        score = 50.0
        trademark = data.get("trademark_strength")
        if trademark is not None:
            score = float(trademark)
        coverage = data.get("geographic_coverage")
        if coverage is not None:
            cov_score = float(coverage)
            score = (score + cov_score) / 2
        return max(0, min(100, score))

    @staticmethod
    def _pillar_rationale(
        pillar_name: str, data: dict[str, Any] | None, score: float
    ) -> str:
        """Build rationale string for a pillar score."""
        if not data:
            return (
                f"{pillar_name.title()} pillar scored"
                " using stub defaults (no data provided)."
            )
        metrics = ", ".join(f"{k}={v}" for k, v in data.items() if k != "score")
        return (
            f"{pillar_name.title()} scored {score:.1f}/100"
            f" based on: {metrics or 'pre-computed score'}."
        )
