"""SKL-TCIA-03: Viral Content Analyzer.

Analyzes viral content patterns, formats, and amplification mechanics.
"""

import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class ViralContentAnalyzer(BaseSkill):
    """Analyze viral content patterns for brand relevance."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-03",
        name="viral_content_analyzer",
        description="Analyze viral content formats and amplification mechanics",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=60000,
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
        persona_platforms = input_data.get("persona_platforms", [])

        query = f"viral content patterns {industry} social media what goes viral 2025 2026"
        try:
            if self._cb_tavily:
                results = await self._cb_tavily.call(
                    self._tavily.search, query, max_results=10
                )
            else:
                results = await self._tavily.search(query, max_results=10)
        except Exception as exc:
            logger.warning("Viral content search failed: %s", exc)
            results = []

        viral_patterns: dict[str, Any] = {
            "top_formats": [],
            "emotional_triggers": [],
            "amplification_mechanics": [],
            "platform_factors": [],
            "brand_safe_patterns": [],
            "brand_unsafe_patterns": [],
        }

        _FORMAT_KEYWORDS = [
            "short video", "meme", "carousel", "thread", "reel",
            "story", "live stream", "duet", "infographic", "poll",
            "listicle", "tutorial", "unboxing", "challenge",
        ]
        _TRIGGER_KEYWORDS = [
            "humor", "surprise", "nostalgia", "outrage", "inspiration",
            "fear of missing out", "empathy", "awe", "curiosity",
            "controversy", "relatability", "shock",
        ]
        _AMPLIFICATION_KEYWORDS = [
            "duet", "stitch", "retweet", "share", "repost",
            "remix", "quote tweet", "comment chain", "save",
            "algorithm boost", "hashtag challenge", "collab",
            "tag a friend", "cross-post", "embed",
        ]
        _BRAND_SAFE_KEYWORDS = [
            "educational", "wholesome", "feel-good", "community",
            "how-to", "tips", "life hack", "diy", "tutorial",
            "behind the scenes", "employee spotlight", "user generated",
        ]
        _BRAND_UNSAFE_KEYWORDS = [
            "controversial", "polarizing", "offensive", "nsfw",
            "cancel culture", "rage bait", "hate", "misinformation",
            "conspiracy", "shock value", "prank gone wrong",
            "dangerous challenge", "self-harm",
        ]

        for r in results:
            content = r.get("content", "").lower()
            url = r.get("url", "").lower()

            # Extract format patterns
            for fmt in _FORMAT_KEYWORDS:
                if fmt in content and fmt not in viral_patterns["top_formats"]:
                    viral_patterns["top_formats"].append(fmt)

            # Extract emotional triggers
            for trigger in _TRIGGER_KEYWORDS:
                if trigger in content and trigger not in viral_patterns["emotional_triggers"]:
                    viral_patterns["emotional_triggers"].append(trigger)

            # Extract amplification mechanics
            for mechanic in _AMPLIFICATION_KEYWORDS:
                if mechanic in content and mechanic not in viral_patterns["amplification_mechanics"]:
                    viral_patterns["amplification_mechanics"].append(mechanic)

            # Extract brand-safe patterns
            for safe in _BRAND_SAFE_KEYWORDS:
                if safe in content and safe not in viral_patterns["brand_safe_patterns"]:
                    viral_patterns["brand_safe_patterns"].append(safe)

            # Extract brand-unsafe patterns
            for unsafe in _BRAND_UNSAFE_KEYWORDS:
                if unsafe in content and unsafe not in viral_patterns["brand_unsafe_patterns"]:
                    viral_patterns["brand_unsafe_patterns"].append(unsafe)

            # Extract platform factors from URL and content
            platform = self._detect_platform(url, content)
            if platform:
                factor = {"platform": platform}
                snippets = self._extract_platform_snippet(content, platform)
                if snippets:
                    factor["factor"] = snippets
                if factor not in viral_patterns["platform_factors"]:
                    viral_patterns["platform_factors"].append(factor)

        # Supplement with persona-platform-specific search
        if persona_platforms:
            platform_query = (
                f"viral content strategy {' '.join(persona_platforms[:3])} "
                f"{industry} amplification 2025 2026"
            )
            try:
                if self._cb_tavily:
                    plat_results = await self._cb_tavily.call(
                        self._tavily.search, platform_query, max_results=5
                    )
                else:
                    plat_results = await self._tavily.search(
                        platform_query, max_results=5
                    )
                for r in plat_results:
                    content = r.get("content", "").lower()
                    for mechanic in _AMPLIFICATION_KEYWORDS:
                        if (
                            mechanic in content
                            and mechanic not in viral_patterns["amplification_mechanics"]
                        ):
                            viral_patterns["amplification_mechanics"].append(mechanic)
            except Exception as exc:
                logger.warning("Platform-specific viral search failed: %s", exc)

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"viral_patterns": viral_patterns},
            duration_ms=elapsed,
        )

    @staticmethod
    def _detect_platform(url: str, content: str) -> str:
        """Detect which platform a result relates to."""
        platform_signals = {
            "tiktok": ["tiktok.com", "tiktok"],
            "instagram": ["instagram.com", "instagram", "reels"],
            "twitter": ["twitter.com", "x.com", "tweet"],
            "youtube": ["youtube.com", "youtu.be", "youtube"],
            "reddit": ["reddit.com", "subreddit"],
            "linkedin": ["linkedin.com", "linkedin"],
            "facebook": ["facebook.com", "facebook"],
            "pinterest": ["pinterest.com", "pinterest"],
        }
        combined = f"{url} {content}"
        for platform, signals in platform_signals.items():
            if any(s in combined for s in signals):
                return platform
        return ""

    @staticmethod
    def _extract_platform_snippet(content: str, platform: str) -> str:
        """Extract a short insight snippet about the platform from content."""
        idx = content.find(platform)
        if idx == -1:
            return ""
        start = max(0, idx - 50)
        end = min(len(content), idx + len(platform) + 100)
        snippet = content[start:end].strip()
        # Trim to sentence boundaries
        dot = snippet.rfind(".")
        if dot > 20:
            snippet = snippet[: dot + 1]
        return snippet[:150]
