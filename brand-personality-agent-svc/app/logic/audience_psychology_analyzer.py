"""SKL-BPV-01: Extract psychographics from APA + VoCA data."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AudiencePsychologyAnalyzer:
    """Analyze audience psychology for personality design."""

    async def analyze(
        self,
        apa_data: dict[str, Any],
        voca_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract psychographic patterns from audience and VoC data."""
        personas = apa_data.get("personas", [])
        pain_points = voca_data.get("pain_point_priority_matrix", {}).get(
            "pain_points", []
        )
        sentiment = voca_data.get("sentiment", {})
        themes = voca_data.get("themes", [])

        return {
            "personas": personas,
            "persona_count": len(personas),
            "pain_points": pain_points,
            "sentiment": sentiment,
            "themes": themes,
            "psychographic_density": self._assess_density(personas),
        }

    def _assess_density(self, personas: list) -> str:
        """Assess psychographic data density."""
        count = len(personas)
        if count <= 1:
            return "low"
        if count <= 3:
            return "moderate"
        return "high"
