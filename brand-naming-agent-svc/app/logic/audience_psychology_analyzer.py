"""SKL-NTA-02: Analyze audience psychographics for name resonance."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AudiencePsychologyAnalyzer:
    """Analyze audience psychology for naming resonance."""

    async def analyze(
        self,
        apa_data: dict[str, Any],
        voca_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract psychographic patterns for naming resonance."""
        personas = apa_data.get("personas", [])
        sentiment = voca_data.get("sentiment", {})
        themes = voca_data.get("themes", [])
        language_patterns = voca_data.get("language_patterns", [])

        # Extract naming-relevant psychographics
        age_ranges = []
        education_levels = []
        values = []
        for persona in personas:
            demo = persona.get("demographics", {})
            if isinstance(demo, dict):
                if demo.get("age_range"):
                    age_ranges.append(demo["age_range"])
                if demo.get("education"):
                    education_levels.append(demo["education"])
            psycho = persona.get("psychographics", {})
            if isinstance(psycho, dict):
                values.extend(psycho.get("values", []))

        return {
            "personas": personas,
            "persona_count": len(personas),
            "sentiment": sentiment,
            "themes": themes,
            "language_patterns": language_patterns,
            "age_ranges": age_ranges,
            "education_levels": education_levels,
            "audience_values": list(set(values)),
            "linguistic_sophistication": self._assess_sophistication(
                education_levels
            ),
        }

    def _assess_sophistication(self, education_levels: list) -> str:
        """Assess linguistic sophistication of target audience."""
        if not education_levels:
            return "moderate"
        high_ed = sum(
            1 for e in education_levels
            if any(kw in str(e).lower() for kw in ("graduate", "master", "phd", "doctoral"))
        )
        if high_ed > len(education_levels) / 2:
            return "high"
        return "moderate"
