"""SKL-APA-01: Audience Landscape Research — Tavily web search for demographics."""

import logging
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class AudienceLandscapeResearch(BaseSkill):
    """Discover audience demographics and segments via Tavily web search."""

    meta = SkillMeta(
        skill_id="SKL-APA-01",
        name="audience_landscape_research",
        description=(
            "Research target audience demographics, segments, and customer "
            "profiles via web search. Seeds from MRA market_overview when available."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Research audience landscape via web search.

        input_data keys:
          - prompt (str): User's analysis query
          - mra_context (dict): Market research data from upstream MRA agent
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")

        if not prompt:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No query provided",
                duration_ms=_elapsed(start),
            )

        # Seed from MRA context if available
        mra_context = input_data.get("mra_context", {})
        market_overview = ""
        if isinstance(mra_context, dict):
            market_overview = mra_context.get("market_overview", "")

        # Build search queries
        search_queries = [
            f"{prompt} target audience demographics",
            f"{prompt} customer segments",
            f"{prompt} buyer persona research",
        ]

        if market_overview:
            # Extract key terms from market overview for enriched search
            overview_snippet = market_overview[:150].split(".")[0]
            search_queries.append(f"{overview_snippet} audience profile")

        # Execute searches
        all_results: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for query in search_queries[:4]:
            results = await self.tavily_client.search(query, max_results=5)
            for r in results:
                all_results.append(r)
                url = r.get("url", "")
                if url:
                    sources.append(
                        {
                            "type": "web",
                            "title": r.get("title", ""),
                            "url": url,
                        }
                    )

        # Extract audience signals from results
        audience_signals = _extract_audience_signals(all_results)

        # Build context string for downstream synthesis
        context_parts = []
        for r in all_results:
            content = r.get("content", "")
            if content:
                context_parts.append(content[:500])

        raw_context = "\n\n".join(context_parts)
        if market_overview:
            raw_context = f"Market Context: {market_overview[:500]}\n\n{raw_context}"

        logger.info(
            "Audience research: %d results, %d signals, %d sources",
            len(all_results),
            len(audience_signals),
            len(sources),
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "context": raw_context[:15000],
                "sources": sources,
                "audience_signals": audience_signals,
                "search_queries_used": search_queries[:4],
                "total_results": len(all_results),
            },
            duration_ms=_elapsed(start),
        )


def _extract_audience_signals(results: list[dict[str, Any]]) -> list[str]:
    """Extract demographic/audience signals from search results."""
    signals: list[str] = []
    seen: set[str] = set()

    keywords = [
        "demographic",
        "age group",
        "income",
        "education",
        "gender",
        "location",
        "urban",
        "rural",
        "millennial",
        "gen z",
        "baby boomer",
        "professional",
        "enterprise",
        "small business",
        "startup",
        "consumer",
        "b2b",
        "b2c",
    ]

    for result in results:
        content = (result.get("content", "") + " " + result.get("title", "")).lower()
        for kw in keywords:
            if kw in content and kw not in seen:
                seen.add(kw)
                signals.append(kw)

    return signals


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
