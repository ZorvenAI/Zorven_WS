"""SKL-CIA-03: Social Media Analyzer — Tavily search for social metrics."""

import logging
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class SocialMediaAnalyzer(BaseSkill):
    """Analyze competitor social media presence via web search."""

    meta = SkillMeta(
        skill_id="SKL-CIA-03",
        name="social_media_analyzer",
        description=(
            "Assess competitor social presence: follower counts, posting cadence, "
            "engagement rates, content strategy patterns."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Analyze competitor social media presence.

        input_data keys:
          - competitors (list): Competitor dicts with {name, slug, website}
          - prompt (str): Original query
        """
        start = time.monotonic()
        competitors = input_data.get("competitors", [])

        if not competitors:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"social_data": [], "competitors_analyzed": 0},
                duration_ms=_elapsed(start),
            )

        social_data: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for comp in competitors:
            name = comp.get("name", "")
            slug = comp.get("slug", "")

            query = f"{name} social media presence LinkedIn Twitter followers"
            results = await self.tavily_client.search(query, max_results=5)

            # Extract social metrics from search results
            platforms: dict[str, dict[str, Any]] = {}
            content_themes: list[str] = []

            for r in results:
                url = r.get("url", "")
                content = r.get("content", "")

                if url:
                    sources.append({
                        "type": "social",
                        "title": f"{name} social - {r.get('title', '')}",
                        "url": url,
                    })

                # Detect platform from URL
                if "linkedin.com" in url:
                    platforms["linkedin"] = _extract_platform_data(content)
                elif "twitter.com" in url or "x.com" in url:
                    platforms["twitter"] = _extract_platform_data(content)
                elif "facebook.com" in url:
                    platforms["facebook"] = _extract_platform_data(content)
                elif "instagram.com" in url:
                    platforms["instagram"] = _extract_platform_data(content)

                # Extract content themes
                themes = _extract_content_themes(content)
                content_themes.extend(themes)

            social_data.append({
                "slug": slug,
                "name": name,
                "platforms": platforms,
                "platform_count": len(platforms),
                "content_themes": list(set(content_themes))[:10],
                "summary": (
                    f"{name} found on {len(platforms)} platforms: "
                    f"{', '.join(platforms.keys()) or 'none detected'}"
                ),
                "data_freshness_warning": (
                    "Social metrics extracted from web search results. "
                    "May not reflect real-time data."
                ),
            })

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "social_data": social_data,
                "competitors_analyzed": len(social_data),
                "sources": sources,
            },
            duration_ms=_elapsed(start),
        )


def _extract_platform_data(content: str) -> dict[str, Any]:
    """Extract social media metrics from search result content."""
    import re

    data: dict[str, Any] = {"raw_snippet": content[:300]}

    # Try to extract follower counts
    follower_patterns = [
        r"([\d,]+\.?\d*[KkMm]?)\s*followers",
        r"followers?\s*:?\s*([\d,]+\.?\d*[KkMm]?)",
    ]
    for pattern in follower_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            data["followers_hint"] = match.group(1)
            break

    return data


def _extract_content_themes(content: str) -> list[str]:
    """Identify content themes from social media text."""
    content_lower = content.lower()
    themes: list[str] = []
    theme_keywords = {
        "educational": ["learn", "how to", "guide", "tutorial", "tips"],
        "promotional": ["launch", "new feature", "announce", "release"],
        "thought_leadership": ["insights", "trends", "future", "industry"],
        "customer_success": ["customer", "case study", "testimonial", "review"],
        "community": ["community", "event", "webinar", "meetup"],
    }
    for theme, keywords in theme_keywords.items():
        if any(kw in content_lower for kw in keywords):
            themes.append(theme)
    return themes


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
