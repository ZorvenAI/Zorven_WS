"""SKL-BAA-06: Architecture model recommendation with 5-model scoring."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

ARCHITECTURE_MODELS = [
    "branded_house",
    "house_of_brands",
    "endorsed",
    "hybrid",
    "sub_brand",
]


class ModelRecommender:
    """Score and recommend architecture models."""

    async def recommend(
        self,
        research: dict[str, Any],
        llm_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract model recommendation from LLM result."""
        recommendation = llm_result.get("recommendation", {})
        model_scores = recommendation.get("model_scores", [])

        # Validate model scores
        validated_scores = []
        for score in model_scores:
            validated_scores.append(
                {
                    "model": score.get("model", "unknown"),
                    "positioning_alignment": min(
                        max(score.get("positioning_alignment", 0), 0), 25
                    ),
                    "audience_fit": min(max(score.get("audience_fit", 0), 0), 25),
                    "competitive_diff": min(
                        max(score.get("competitive_diff", 0), 0), 25
                    ),
                    "operational_efficiency": min(
                        max(score.get("operational_efficiency", 0), 0), 25
                    ),
                    "total": min(max(score.get("total", 0), 0), 100),
                    "rationale": score.get("rationale", ""),
                }
            )

        return {
            "recommended_model": recommendation.get("recommended_model", "hybrid"),
            "model_scores": validated_scores,
            "why_not_others": recommendation.get("why_not_others", []),
            "confidence_score": recommendation.get("confidence_score", 0.0),
            "citations": recommendation.get("citations", []),
        }
