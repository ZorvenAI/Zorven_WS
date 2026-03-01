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
        brand_seed: str = "",
    ) -> BSIResult:
        """
        Calculate BSI from available pillar data.

        Args:
            financial_data: Revenue growth, margins, market share metrics.
            behavioral_data: Awareness, sentiment, loyalty metrics.
            legal_data: Trademark, geographic coverage metrics.
            weights: Custom pillar weights (default: 40/35/25).
            brand_seed: Brand/company name used to vary stub scores
                so different brands produce distinct BSI values.

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
            # No data at all — return zero score with clear error
            logger.warning(
                "BSI: No pillar data available. Cannot calculate Brand "
                "Strength Index without financial, behavioral, or legal data."
            )
            return BSIResult(
                score=0,
                pillars=[
                    PillarScore(
                        name=name,
                        weight=round(base_weights[name], 4),
                        score=0.0,
                        rationale=(
                            f"{name.title()} data not available. "
                            f"Provide {name} metrics for an accurate BSI."
                        ),
                    )
                    for name in DEFAULT_WEIGHTS
                ],
                data_completeness=0.0,
            )
        else:
            effective_weights = base_weights

        # Score each pillar
        pillar_scores: list[PillarScore] = []
        weighted_sum = 0.0

        for pillar_name in available_pillars:
            data = pillar_data.get(pillar_name)
            weight = effective_weights.get(pillar_name, 0.0)
            score = self._score_pillar(pillar_name, data, brand_seed=brand_seed)
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

    def _score_pillar(
        self,
        pillar_name: str,
        data: dict[str, Any] | None,
        brand_seed: str = "",
    ) -> float:
        """Score a single pillar (0–100). Returns 0 when no data."""
        if not data:
            return 0.0

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

        return 0.0

    @staticmethod
    def _score_financial(data: dict[str, Any]) -> float:
        """Score financial pillar from metrics.

        Scoring bands:
          Revenue growth: <3%=30, 3-8%=50-65, 8-15%=65-80, 15-30%=80-90, >30%=90+
          Profit margin:  <0%=20, 0-5%=35-50, 5-15%=50-70, 15-25%=70-85, >25%=85+
          Market share:   0-5%=30-50, 5-20%=50-75, 20-40%=75-90, >40%=90+
        """
        score = 50.0  # Base score

        growth = data.get("revenue_growth")
        if growth is not None:
            g = float(growth)
            if g < 0:
                score = max(10, 30 + g * 100)    # Negative growth penalized
            elif g < 0.03:
                score = 30 + g * 667             # 0-3% → 30-50
            elif g < 0.08:
                score = 50 + (g - 0.03) * 300    # 3-8% → 50-65
            elif g < 0.15:
                score = 65 + (g - 0.08) * 214    # 8-15% → 65-80
            elif g < 0.30:
                score = 80 + (g - 0.15) * 67     # 15-30% → 80-90
            else:
                score = min(100, 90 + (g - 0.30) * 33)  # >30% → 90+

        margin = data.get("profit_margin")
        if margin is not None:
            m = float(margin)
            if m < 0:
                margin_score = max(10, 20 + m * 100)    # Negative margin
            elif m < 0.05:
                margin_score = 35 + m * 300              # 0-5% → 35-50
            elif m < 0.15:
                margin_score = 50 + (m - 0.05) * 200    # 5-15% → 50-70
            elif m < 0.25:
                margin_score = 70 + (m - 0.15) * 150    # 15-25% → 70-85
            else:
                margin_score = min(100, 85 + (m - 0.25) * 60)  # >25% → 85+
            score = (score + margin_score) / 2

        market_share = data.get("market_share")
        if market_share is not None:
            ms = float(market_share)
            if ms < 0.05:
                share_score = 30 + ms * 400          # 0-5% → 30-50
            elif ms < 0.20:
                share_score = 50 + (ms - 0.05) * 167  # 5-20% → 50-75
            elif ms < 0.40:
                share_score = 75 + (ms - 0.20) * 75   # 20-40% → 75-90
            else:
                share_score = min(100, 90 + (ms - 0.40) * 17)  # >40% → 90+
            score = (score * 2 + share_score) / 3

        return max(0, min(100, score))

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
                f"{pillar_name.title()} data not available. "
                f"Provide {pillar_name} metrics for an accurate score."
            )
        metrics = ", ".join(f"{k}={v}" for k, v in data.items() if k != "score")
        return (
            f"{pillar_name.title()} scored {score:.1f}/100"
            f" based on: {metrics or 'pre-computed score'}."
        )
