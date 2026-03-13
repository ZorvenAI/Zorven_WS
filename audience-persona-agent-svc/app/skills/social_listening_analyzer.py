"""SKL-APA-03: Social Listening Analyzer — Platform behavior patterns."""

import logging
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class SocialListeningAnalyzer(BaseSkill):
    """Analyze social media behavior patterns and platform preferences."""

    meta = SkillMeta(
        skill_id="SKL-APA-03",
        name="social_listening_analyzer",
        description=(
            "Search for social media behavior patterns, platform preferences, "
            "content consumption habits, and influencer engagement patterns."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Analyze social media behavior patterns.

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

        # Platform-specific queries
        search_queries = [
            f"{prompt} social media behavior content preferences",
            f"{prompt} LinkedIn Twitter Instagram engagement patterns",
            f"{prompt} influencer marketing audience platform usage",
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
                            "type": "web",
                            "title": r.get("title", ""),
                            "url": url,
                        }
                    )

        # Extract platform behaviors
        platform_behaviors = _extract_platform_behaviors(all_results)

        # Build context
        context_parts = []
        for r in all_results:
            content = r.get("content", "")
            if content:
                context_parts.append(content[:400])

        raw_context = "\n\n".join(context_parts)

        logger.info(
            "Social listening: %d results, %d platform behaviors",
            len(all_results),
            len(platform_behaviors),
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "context": raw_context[:15000],
                "sources": sources,
                "platform_behaviors": platform_behaviors,
            },
            duration_ms=_elapsed(start),
        )


def _extract_platform_behaviors(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract platform-specific behavior patterns."""
    platforms = {
        "linkedin": "LinkedIn",
        "twitter": "Twitter/X",
        "instagram": "Instagram",
        "facebook": "Facebook",
        "tiktok": "TikTok",
        "youtube": "YouTube",
        "reddit": "Reddit",
    }

    behaviors: list[dict[str, str]] = []
    seen_platforms: set[str] = set()

    for result in results:
        content = (result.get("content", "") + " " + result.get("title", "")).lower()
        for key, name in platforms.items():
            if key in content and key not in seen_platforms:
                seen_platforms.add(key)
                # Extract snippet about this platform
                idx = content.find(key)
                snippet_start = max(0, idx - 30)
                snippet_end = min(len(content), idx + 150)
                snippet = content[snippet_start:snippet_end].strip()
                behaviors.append(
                    {
                        "platform": name,
                        "insight": snippet[:200],
                    }
                )

    return behaviors


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
