"""SKL-BAA-02: Audience alignment from APA + VoCA + BPA needs hierarchy."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AudienceAlignment:
    """Align audience personas with brand architecture needs."""

    async def align(
        self,
        apa_data: dict[str, Any],
        voca_data: dict[str, Any],
        bpa_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract and align audience data for architecture decisions."""
        personas = apa_data.get("personas", [])
        pain_points = voca_data.get("pain_point_priority_matrix", {}).get(
            "pain_points", []
        )
        needs_hierarchy = bpa_data.get("differentiation", {}).get("pods", [])

        return {
            "personas": personas,
            "persona_count": len(personas),
            "pain_points": pain_points,
            "needs_hierarchy": needs_hierarchy,
            "segment_diversity": self._assess_diversity(personas),
        }

    def _assess_diversity(self, personas: list) -> str:
        """Assess segment diversity for architecture implications."""
        count = len(personas)
        if count <= 1:
            return "low"
        if count <= 3:
            return "moderate"
        return "high"
