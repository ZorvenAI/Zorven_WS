"""SKL-TCIA-01: Social Trend Scanner.

Scans social media platforms for trending topics via Tavily search + httpx.
"""

import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class SocialTrendScanner(BaseSkill):
    """Scan social platforms for trending topics relevant to the brand."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-01",
        name="social_trend_scanner",
        description="Scan social media platforms for trending topics",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(
        self,
        tavily_client: Any,
        scraper_client: Any,
        cb_tavily: Any = None,
        cb_httpx: Any = None,
    ) -> None:
        self._tavily = tavily_client
        self._scraper = scraper_client
        self._cb_tavily = cb_tavily
        self._cb_httpx = cb_httpx

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()
        industry = input_data.get("industry", "")
        persona_keywords = input_data.get("persona_keywords", [])
        platforms = input_data.get(
            "platforms", ["twitter", "tiktok", "reddit", "linkedin", "instagram"]
        )
        lookback_hours = input_data.get("lookback_hours", 72)

        social_trends: list[dict[str, Any]] = []

        for platform in platforms:
            keywords_str = " ".join(persona_keywords[:3]) if persona_keywords else ""
            query = (
                f"{platform} trending topics {industry} "
                f"{keywords_str} last {lookback_hours} hours"
            ).strip()

            try:
                if self._cb_tavily:
                    results = await self._cb_tavily.call(
                        self._tavily.search, query, max_results=5
                    )
                else:
                    results = await self._tavily.search(query, max_results=5)

                for r in results:
                    content = r.get("content", "")
                    social_trends.append(
                        {
                            "topic": r.get("title", ""),
                            "platform": platform,
                            "velocity_score": 0.5,
                            "volume_estimate": 0,
                            "hashtags": self._extract_hashtags(content),
                            "sample_content_urls": [r.get("url", "")],
                        }
                    )
            except Exception as exc:
                logger.warning("Social scan failed for %s: %s", platform, exc)

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"social_trends": social_trends},
            duration_ms=elapsed,
        )

    @staticmethod
    def _extract_hashtags(text: str) -> list[str]:
        """Extract hashtags from text."""
        return [
            word
            for word in text.split()
            if word.startswith("#") and len(word) > 1
        ][:10]
