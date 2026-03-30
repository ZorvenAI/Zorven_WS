"""SKL-CAA-05: RAG Intelligence Retriever.

Searches RAG for prior campaign learnings. Returns empty
PriorCampaignLearnings for first campaign (graceful degradation).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RAGIntelligenceRetriever:
    """Retrieve and structure prior campaign learnings from RAG."""

    def process(self, rag_context: dict[str, Any] | None) -> dict[str, Any]:
        """Process RAG learnings into structured campaign intelligence."""
        if not rag_context:
            return {
                "available": False,
                "learnings": [],
                "audience_insights": [],
                "funnel_insights": [],
                "budget_insights": [],
                "competitive_insights": [],
            }

        learnings = rag_context.get("learnings", [])
        audience_insights = []
        funnel_insights = []
        budget_insights = []
        competitive_insights = []

        for learning in learnings:
            data = learning.get("data", {})
            category = data.get("category", "")
            if category == "audience":
                audience_insights.append(data)
            elif category == "funnel":
                funnel_insights.append(data)
            elif category == "budget":
                budget_insights.append(data)
            elif category == "competitive":
                competitive_insights.append(data)

        return {
            "available": True,
            "learnings": learnings,
            "audience_insights": audience_insights,
            "funnel_insights": funnel_insights,
            "budget_insights": budget_insights,
            "competitive_insights": competitive_insights,
        }

    def build_prompt_section(self, intelligence: dict[str, Any]) -> str:
        """Build prior learnings prompt section for LLM call."""
        if not intelligence.get("available"):
            return (
                "## Prior Campaign Learnings\n\n"
                "No prior campaign data available. "
                "This is the first campaign — design from scratch.\n"
            )

        section = "## Prior Campaign Learnings (RAG)\n\n"
        for category, insights in [
            ("Audience", intelligence.get("audience_insights", [])),
            ("Funnel", intelligence.get("funnel_insights", [])),
            ("Budget", intelligence.get("budget_insights", [])),
            ("Competitive", intelligence.get("competitive_insights", [])),
        ]:
            if insights:
                section += f"### {category} Insights\n"
                for ins in insights[:3]:
                    section += f"- {ins.get('summary', str(ins))}\n"
        return section
