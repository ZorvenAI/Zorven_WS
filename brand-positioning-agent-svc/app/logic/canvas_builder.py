"""SKL-BPA-07: Value Proposition Canvas Builder.

Builds Osterwalder Value Proposition Canvas: customer profile
(jobs, pains, gains) mapped to value map (products, pain relievers,
gain creators).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CanvasBuilder:
    """Builds Value Proposition Canvas from research data."""

    async def build(
        self,
        audience_needs: dict[str, Any],
        positioning: dict[str, Any],
    ) -> dict[str, Any]:
        """Build Value Proposition Canvas.

        Returns:
            Canvas with customer_profile, value_map, fit_score.
        """
        return {
            "customer_profile": {
                "jobs": self._extract_jobs(audience_needs),
                "pains": self._extract_pains(audience_needs),
                "gains": self._extract_gains(audience_needs),
            },
            "value_map": {
                "products": [],
                "pain_relievers": [],
                "gain_creators": [],
            },
            "fit_score": 0.0,
            "fit_analysis": "",
        }

    def _extract_jobs(self, audience_needs: dict[str, Any]) -> list[str]:
        """Extract customer jobs from persona data."""
        jobs = []
        for persona in audience_needs.get("persona_summaries", []):
            if isinstance(persona, dict):
                label = persona.get("label", "")
                if label:
                    jobs.append(f"Jobs of {label}")
        return jobs

    def _extract_pains(self, audience_needs: dict[str, Any]) -> list[str]:
        """Extract customer pains from table-stakes and pain points."""
        pains = []
        for need in audience_needs.get("table_stakes", []):
            if isinstance(need, dict):
                pains.append(need.get("name", ""))
        return [p for p in pains if p]

    def _extract_gains(self, audience_needs: dict[str, Any]) -> list[str]:
        """Extract customer gains from delighters."""
        gains = []
        for need in audience_needs.get("delighters", []):
            if isinstance(need, dict):
                gains.append(need.get("name", ""))
        return [g for g in gains if g]
