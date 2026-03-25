"""PG-07: Sub-brand Aaker deviation validator (±20 points from parent)."""

import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


class SubBrandConstraint:
    """Validate sub-brand Aaker scores stay within ±20 of parent."""

    MAX_DEVIATION = 20  # ±20 points on 0-100 scale

    async def validate(
        self,
        parent_personality: dict[str, Any],
        sub_brand_personality: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and adjust sub-brand Aaker scores.

        Returns adjusted profile + list of constraint violations.
        """
        violations = []
        adjusted = deepcopy(sub_brand_personality)

        parent_dims = {}
        for d in parent_personality.get("aaker_profile", {}).get("dimensions", []):
            parent_dims[d["dimension"]] = d["score"]

        for dim in adjusted.get("aaker_profile", {}).get("dimensions", []):
            parent_score = parent_dims.get(dim["dimension"])
            if parent_score is None:
                continue

            deviation = dim["score"] - parent_score
            if abs(deviation) > self.MAX_DEVIATION:
                clamped = parent_score + (
                    self.MAX_DEVIATION if deviation > 0 else -self.MAX_DEVIATION
                )
                clamped = min(max(clamped, 0), 100)
                violations.append({
                    "dimension": dim["dimension"],
                    "parent_score": parent_score,
                    "original_score": dim["score"],
                    "adjusted_score": clamped,
                })
                dim["score"] = clamped
                logger.info(
                    "PG-07: %s clamped from %.0f to %.0f (parent: %.0f)",
                    dim["dimension"],
                    violations[-1]["original_score"],
                    clamped,
                    parent_score,
                )

        return {"adjusted_personality": adjusted, "violations": violations}
