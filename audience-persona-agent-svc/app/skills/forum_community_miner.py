"""SKL-APA-02: Forum & Community Miner — Reddit, Quora, and forum insights."""

import logging
import time
from typing import Any

from app.services.api_clients import TavilySearchClient, WebScraperClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class ForumCommunityMiner(BaseSkill):
    """Mine forums and communities for pain points, language, and sentiment."""

    meta = SkillMeta(
        skill_id="SKL-APA-02",
        name="forum_community_miner",
        description=(
            "Search Reddit, Quora, and industry forums for pain points, "
            "community language patterns, and sentiment signals. "
            "Respects robots.txt (PG-09)."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(
        self,
        tavily_client: TavilySearchClient,
        web_scraper: WebScraperClient,
    ) -> None:
        self.tavily_client = tavily_client
        self.web_scraper = web_scraper

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Mine forums for audience insights.

        input_data keys:
          - prompt (str): User's analysis query
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

        # Forum-specific search queries
        search_queries = [
            f"site:reddit.com {prompt} pain points frustrations",
            f"site:quora.com {prompt} challenges problems",
            f"{prompt} forum discussion community feedback",
        ]

        all_results: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for query in search_queries:
            results = await self.tavily_client.search(query, max_results=5)
            for r in results:
                all_results.append(r)
                url = r.get("url", "")
                if url:
                    sources.append(
                        {
                            "type": "forum",
                            "title": r.get("title", ""),
                            "url": url,
                        }
                    )

        # Extract community insights
        community_insights = _extract_community_insights(all_results)
        language_patterns = _extract_language_patterns(all_results)

        # Build context
        context_parts = []
        for r in all_results:
            content = r.get("content", "")
            if content:
                context_parts.append(f"[{r.get('title', 'Forum')}]: {content[:400]}")

        raw_context = "\n\n".join(context_parts)

        logger.info(
            "Forum mining: %d results, %d insights, %d patterns",
            len(all_results),
            len(community_insights),
            len(language_patterns),
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "context": raw_context[:15000],
                "sources": sources,
                "community_insights": community_insights,
                "language_patterns": language_patterns,
            },
            duration_ms=_elapsed(start),
        )


def _extract_community_insights(results: list[dict[str, Any]]) -> list[str]:
    """Extract pain points and insights from forum content."""
    insights: list[str] = []
    pain_keywords = [
        "frustrat",
        "annoying",
        "difficult",
        "struggle",
        "problem",
        "issue",
        "hate",
        "wish",
        "need",
        "looking for",
        "anyone know",
        "recommend",
        "alternative",
        "switch",
        "better than",
    ]

    for result in results:
        content = result.get("content", "").lower()
        for kw in pain_keywords:
            if kw in content:
                # Extract sentence around the keyword
                idx = content.find(kw)
                snippet_start = max(0, idx - 50)
                snippet_end = min(len(content), idx + 100)
                snippet = content[snippet_start:snippet_end].strip()
                if snippet and len(snippet) > 20:
                    insights.append(snippet)
                break  # One insight per result

    return insights[:20]


def _extract_language_patterns(results: list[dict[str, Any]]) -> list[str]:
    """Extract common phrases and language patterns from community content."""
    patterns: list[str] = []
    seen: set[str] = set()

    phrase_markers = [
        "i need",
        "i want",
        "i wish",
        "looking for",
        "the best",
        "the worst",
        "compared to",
        "instead of",
        "my team",
        "our company",
        "my business",
    ]

    for result in results:
        content = result.get("content", "").lower()
        for marker in phrase_markers:
            if marker in content and marker not in seen:
                idx = content.find(marker)
                end = min(len(content), idx + 80)
                phrase = content[idx:end].split(".")[0].strip()
                if phrase and len(phrase) > 10:
                    seen.add(marker)
                    patterns.append(phrase)

    return patterns[:15]


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
