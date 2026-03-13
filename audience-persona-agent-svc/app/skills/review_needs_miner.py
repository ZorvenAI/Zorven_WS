"""SKL-APA-05: Review & Needs Miner — Product reviews, needs, and objections."""

import logging
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class ReviewNeedsMiner(BaseSkill):
    """Mine product reviews for needs, objections, and decision criteria."""

    meta = SkillMeta(
        skill_id="SKL-APA-05",
        name="review_needs_miner",
        description=(
            "Search G2, Capterra, TrustRadius, and general review sites "
            "for customer needs, objections, and decision criteria. "
            "Seeded by CIA competitor list when available."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Mine reviews for needs and objections.

        input_data keys:
          - prompt (str): User's analysis query
          - cia_context (dict): Competitor intelligence from upstream CIA agent
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

        # Seed from CIA competitor list if available
        cia_context = input_data.get("cia_context", {})
        competitors = []
        if isinstance(cia_context, dict):
            competitors = cia_context.get("competitors", [])

        # Build review-focused search queries
        search_queries = [
            f"{prompt} product reviews customer feedback",
            f"{prompt} G2 Capterra reviews pros cons",
            f"{prompt} buyer objections purchase barriers",
        ]

        # Add competitor-specific review queries
        for comp in competitors[:2]:
            name = comp.get("name", "") if isinstance(comp, dict) else str(comp)
            if name:
                search_queries.append(f"{name} reviews customer complaints wishlist")

        all_results: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for query in search_queries[:5]:
            results = await self.tavily_client.search(query, max_results=5)
            for r in results:
                all_results.append(r)
                url = r.get("url", "")
                if url:
                    sources.append(
                        {
                            "type": "review",
                            "title": r.get("title", ""),
                            "url": url,
                        }
                    )

        # Extract needs and objections
        needs = _extract_needs(all_results)
        objections = _extract_objections(all_results)

        # Build context
        context_parts = []
        for r in all_results:
            content = r.get("content", "")
            if content:
                context_parts.append(content[:400])

        raw_context = "\n\n".join(context_parts)

        logger.info(
            "Review mining: %d results, %d needs, %d objections",
            len(all_results),
            len(needs),
            len(objections),
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "context": raw_context[:15000],
                "sources": sources,
                "needs": needs,
                "objections": objections,
            },
            duration_ms=_elapsed(start),
        )


def _extract_needs(results: list[dict[str, Any]]) -> list[str]:
    """Extract customer needs from review content."""
    needs: list[str] = []
    need_keywords = [
        "need",
        "want",
        "require",
        "looking for",
        "wish",
        "must have",
        "essential",
        "critical",
        "important",
        "feature request",
        "missing",
        "lack",
    ]

    for result in results:
        content = result.get("content", "").lower()
        for kw in need_keywords:
            if kw in content:
                idx = content.find(kw)
                snippet_start = max(0, idx - 20)
                snippet_end = min(len(content), idx + 100)
                snippet = content[snippet_start:snippet_end].strip()
                if snippet and len(snippet) > 15:
                    needs.append(snippet)
                break

    return needs[:15]


def _extract_objections(results: list[dict[str, Any]]) -> list[str]:
    """Extract buyer objections from review content."""
    objections: list[str] = []
    objection_keywords = [
        "expensive",
        "costly",
        "overpriced",
        "complicated",
        "difficult",
        "steep learning",
        "poor support",
        "unreliable",
        "slow",
        "buggy",
        "concern",
        "downside",
        "con",
        "disadvantage",
        "limitation",
    ]

    for result in results:
        content = result.get("content", "").lower()
        for kw in objection_keywords:
            if kw in content:
                idx = content.find(kw)
                snippet_start = max(0, idx - 20)
                snippet_end = min(len(content), idx + 100)
                snippet = content[snippet_start:snippet_end].strip()
                if snippet and len(snippet) > 15:
                    objections.append(snippet)
                break

    return objections[:15]


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
