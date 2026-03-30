"""SKL-CAA-03: Competitor Ad Analyzer.

Uses Tavily search results + CIA competitor data to analyze competitor
advertising patterns on Meta (ad formats, messaging, frequency).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CompetitorAdAnalyzer:
    """Analyze competitor ad patterns from Tavily + CIA data."""

    def process(
        self,
        tavily_results: dict[str, Any],
        cia_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process competitor ad research into structured analysis."""
        competitors = []
        if cia_data:
            for comp in cia_data.get("competitors", [])[:5]:
                name = comp.get("name", "") if isinstance(comp, dict) else str(comp)
                if name:
                    competitors.append(name)

        return {
            "competitors_analyzed": competitors,
            "tavily_insights": tavily_results.get("answer", ""),
            "sources": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                }
                for r in tavily_results.get("results", [])
            ],
            "competitor_count": len(competitors),
        }

    def build_prompt_section(self, analysis: dict[str, Any]) -> str:
        """Build competitor landscape prompt section for LLM call."""
        competitors = analysis.get("competitors_analyzed", [])
        insights = analysis.get("tavily_insights", "")

        section = "## Competitive Advertising Landscape\n\n"
        if competitors:
            section += f"Key competitors: {', '.join(competitors)}\n"
        if insights:
            section += f"\nCompetitive insights: {insights}\n"
        if not competitors and not insights:
            section += "No competitor advertising data available.\n"
        return section
