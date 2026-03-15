"""SKL-VoCA-06: Social Media Feedback Collector — Brand mentions across social platforms."""

import logging
import time
import uuid
from typing import Any

from app.registry.models import SocialFeedback
from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

# Social platforms to search
_SOCIAL_PLATFORMS = [
    {"name": "Twitter/X", "site_filter": "twitter.com OR x.com"},
    {"name": "LinkedIn", "site_filter": "linkedin.com"},
    {"name": "Reddit", "site_filter": "reddit.com"},
    {"name": "Instagram", "site_filter": "instagram.com"},
    {"name": "Facebook", "site_filter": "facebook.com"},
]

# Engagement signal keywords
_ENGAGEMENT_KEYWORDS = [
    "likes",
    "retweet",
    "shares",
    "comments",
    "upvote",
    "viral",
    "trending",
    "engagement",
    "followers",
    "impressions",
]


class SocialFeedbackCollector(BaseSkill):
    """Collect brand mentions and feedback from social media platforms."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-06",
        name="social_feedback_collector",
        description=(
            "Collects brand mentions and customer feedback from "
            "Twitter/X, LinkedIn, Reddit, Instagram, and Facebook. "
            "Cross-references with TCIA trend data when available."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Collect social media feedback for the brand.

        input_data keys:
          - company_name (str): Brand/company name to search mentions for
          - prompt (str): Additional search context

        context.previous_outputs:
          - trend_cultural (dict): TCIA trend data for cross-referencing
        """
        start = time.monotonic()
        company_name = input_data.get("company_name", "")

        if not company_name:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No company_name provided",
                duration_ms=_elapsed(start),
            )

        try:
            social_feedback: list[dict[str, Any]] = []
            sources: list[dict[str, str]] = []

            # Cross-reference TCIA trend data for trend-driven mentions
            tcia_data = context.previous_outputs.get("trend_cultural", {})
            trend_keywords = _extract_trend_keywords(tcia_data)

            # Search each social platform
            for platform in _SOCIAL_PLATFORMS:
                search_query = (
                    f"{company_name} {platform['site_filter']} "
                    f"feedback opinions mentions"
                )
                results = await self.tavily_client.search(search_query, max_results=5)

                for r in results:
                    url = r.get("url", "")
                    content = r.get("content", "")
                    title = r.get("title", "")

                    # Detect hashtags in content
                    hashtags = _extract_hashtags(content)

                    # Check if this mention is trend-driven (TCIA cross-ref)
                    is_trend = _is_trend_driven(content, trend_keywords)

                    # Estimate engagement from content signals
                    engagement = _estimate_engagement(content)

                    feedback = SocialFeedback(
                        feedback_id=f"social-{uuid.uuid4().hex[:12]}",
                        text=content[:2000],
                        platform=platform["name"],
                        engagement_count=engagement,
                        is_trend_driven=is_trend,
                        hashtags=hashtags,
                        metadata={
                            "source_url": url,
                            "title": title,
                            "trend_keywords_matched": [
                                kw
                                for kw in trend_keywords
                                if kw.lower() in content.lower()
                            ],
                        },
                    )
                    social_feedback.append(feedback.model_dump())

                    if url:
                        sources.append(
                            {
                                "type": "social",
                                "title": title,
                                "url": url,
                                "platform": platform["name"],
                            }
                        )

            logger.info(
                "Social feedback for '%s': %d mentions from %d platforms, "
                "%d trend-driven",
                company_name,
                len(social_feedback),
                len(_SOCIAL_PLATFORMS),
                sum(1 for f in social_feedback if f.get("is_trend_driven", False)),
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "social_feedback": social_feedback,
                    "sources": sources,
                },
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.error(
                "Social feedback collection failed for '%s': %s",
                company_name,
                exc,
            )
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _extract_trend_keywords(tcia_data: dict[str, Any]) -> list[str]:
    """Extract trending keywords from TCIA upstream data."""
    keywords: list[str] = []

    if not isinstance(tcia_data, dict):
        return keywords

    # Extract from trend topics
    trends = tcia_data.get("trends", tcia_data.get("trend_topics", []))
    if isinstance(trends, list):
        for trend in trends[:10]:
            if isinstance(trend, dict):
                name = trend.get("name", trend.get("topic", ""))
                if name:
                    keywords.append(name)
            elif isinstance(trend, str):
                keywords.append(trend)

    # Extract from cultural signals
    signals = tcia_data.get("cultural_signals", [])
    if isinstance(signals, list):
        for signal in signals[:5]:
            if isinstance(signal, dict):
                label = signal.get("label", signal.get("signal", ""))
                if label:
                    keywords.append(label)

    return keywords


def _extract_hashtags(content: str) -> list[str]:
    """Extract hashtags from social media content."""
    import re

    return re.findall(r"#(\w+)", content)[:20]


def _is_trend_driven(content: str, trend_keywords: list[str]) -> bool:
    """Check if content is driven by known trends from TCIA."""
    if not trend_keywords:
        return False
    lower = content.lower()
    return any(kw.lower() in lower for kw in trend_keywords)


def _estimate_engagement(content: str) -> int:
    """Estimate engagement count from content signals."""
    import re

    lower = content.lower()

    # Look for explicit engagement numbers
    for kw in _ENGAGEMENT_KEYWORDS:
        if kw in lower:
            idx = lower.find(kw)
            surrounding = lower[max(0, idx - 30) : idx + len(kw) + 30]
            numbers = re.findall(r"(\d[\d,]*)", surrounding)
            for num_str in numbers:
                try:
                    val = int(num_str.replace(",", ""))
                    if val > 0:
                        return val
                except ValueError:
                    continue

    return 0


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
