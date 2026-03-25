"""SKL-BPV-05: Validate and normalize Aaker 5D personality scores."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

AAKER_DIMENSIONS = [
    "Sincerity", "Excitement", "Competence", "Sophistication", "Ruggedness",
]


class AakerProfiler:
    """Validate and normalize Aaker 5-dimension personality profile."""

    async def validate(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Validate Aaker profile, clamp scores, identify primary/secondary."""
        dimensions = profile.get("dimensions", [])
        validated = []

        for dim in dimensions:
            score = min(max(float(dim.get("score", 0)), 0), 100)
            validated.append({
                "dimension": dim.get("dimension", ""),
                "score": score,
                "rationale": dim.get("rationale", ""),
            })

        # Ensure all 5 dimensions present
        existing = {d["dimension"] for d in validated}
        for dim_name in AAKER_DIMENSIONS:
            if dim_name not in existing:
                validated.append({
                    "dimension": dim_name,
                    "score": 0,
                    "rationale": "",
                })

        # Sort by score descending to identify primary/secondary
        sorted_dims = sorted(validated, key=lambda d: d["score"], reverse=True)
        primary = sorted_dims[0]["dimension"] if sorted_dims else ""
        secondary = sorted_dims[1]["dimension"] if len(sorted_dims) > 1 else ""

        # Override with LLM's choice if provided
        primary = profile.get("primary_dimension", "") or primary
        secondary = profile.get("secondary_dimension", "") or secondary

        # Differentiation: max_score - avg of others
        scores = [d["score"] for d in validated]
        if scores:
            max_score = max(scores)
            others = [s for s in scores if s != max_score]
            avg_others = sum(others) / len(others) if others else 0
            diff_score = round(max_score - avg_others, 1)
        else:
            diff_score = 0.0

        return {
            "dimensions": validated,
            "primary_dimension": primary,
            "secondary_dimension": secondary,
            "differentiation_score": profile.get(
                "differentiation_score", diff_score
            ),
        }
