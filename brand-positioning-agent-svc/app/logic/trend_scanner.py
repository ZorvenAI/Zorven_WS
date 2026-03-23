"""SKL-BPA-03: Trend Scanner.

Analyzes TCIA trend data to produce a trend-positioning affinity matrix.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TrendScanner:
    """Scans trend data for positioning alignment opportunities."""

    async def scan(self, tcia_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze trends for positioning alignment.

        Returns:
            Trend analysis with affinity scores and alignment opportunities.
        """
        scored_trends = tcia_data.get("scored_trends", [])
        cultural_shifts = tcia_data.get("cultural_shifts", [])
        opportunity_alerts = tcia_data.get("opportunity_alerts", [])

        # Filter high-relevance trends
        high_relevance = [
            t
            for t in scored_trends
            if isinstance(t, dict) and t.get("relevance_score", 0) >= 70
        ]

        return {
            "total_trends": len(scored_trends),
            "high_relevance_trends": high_relevance,
            "cultural_shifts": cultural_shifts,
            "opportunity_alerts": opportunity_alerts,
            "trend_positioning_affinity": self._compute_affinity(high_relevance),
        }

    def _compute_affinity(self, trends: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compute trend-positioning affinity matrix."""
        return [
            {
                "trend": t.get("topic", ""),
                "relevance_score": t.get("relevance_score", 0),
                "positioning_opportunity": (
                    "high" if t.get("relevance_score", 0) >= 85 else "medium"
                ),
            }
            for t in trends
        ]
