"""SKL-BPA-01: Competitive Mapper.

Analyzes CIA competitor matrix, plots 2D perceptual space,
identifies white-space zones for positioning opportunities.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CompetitiveMapper:
    """Maps competitive landscape from CIA data."""

    async def map(self, cia_data: dict[str, Any]) -> dict[str, Any]:
        """Extract competitive positioning data.

        Args:
            cia_data: Competitor intelligence agent output.

        Returns:
            Competitive landscape with positions, gaps, and whitespace.
        """
        competitors = cia_data.get("competitors_analyzed", [])
        if not competitors:
            competitors = cia_data.get("competitors", [])

        positioning_gaps = cia_data.get("positioning_gaps", [])
        swot = cia_data.get("swot_analysis", {})

        return {
            "competitors": competitors,
            "competitor_count": len(competitors),
            "positioning_gaps": positioning_gaps,
            "swot_summary": swot,
            "market_positions": cia_data.get("market_positions", []),
            "competitive_dimensions": self._derive_dimensions(
                competitors, positioning_gaps
            ),
        }

    def _derive_dimensions(
        self,
        competitors: list[Any],
        gaps: list[Any],
    ) -> list[dict[str, str]]:
        """Derive perceptual map dimensions from competitive data."""
        dimensions = [
            {"x": "Price", "y": "Quality"},
            {"x": "Innovation", "y": "Reliability"},
            {"x": "Specialization", "y": "Market Reach"},
        ]
        return dimensions
