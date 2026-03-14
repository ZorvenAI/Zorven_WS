"""SKL-TCIA-04: Generational Preference Tracker.

Tracks generation-specific behaviors, language, platforms, and brand expectations.
"""

import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


_LANGUAGE_MARKERS: dict[str, list[str]] = {
    "gen_z": [
        "no cap", "slay", "rizz", "bussin", "bet", "fr fr",
        "ate", "sus", "vibe check", "main character", "delulu",
        "brainrot", "aura", "skibidi", "gyatt",
    ],
    "millennial": [
        "adulting", "fomo", "lowkey", "highkey", "salty", "extra",
        "cancelled", "stan", "mood", "aesthetic", "flex",
    ],
    "gen_x": [
        "whatever", "talk to the hand", "rad", "gnarly", "psych",
    ],
    "boomer": [
        "back in my day", "millennials", "kids these days",
    ],
}

_PLATFORM_KEYWORDS = [
    "tiktok", "instagram", "youtube", "snapchat", "twitter",
    "reddit", "linkedin", "facebook", "discord", "threads",
    "bluesky", "mastodon", "twitch", "pinterest", "bereal",
    "lemon8", "substack", "whatsapp", "telegram",
]

_BRAND_EXPECTATION_KEYWORDS = [
    "authenticity", "transparency", "sustainability", "social responsibility",
    "personalization", "diversity", "inclusivity", "purpose-driven",
    "ethical", "eco-friendly", "community", "mental health",
    "privacy", "data protection", "fast delivery", "seamless experience",
    "user-generated", "co-creation", "loyalty program",
]

_SUBCULTURE_KEYWORDS = [
    "cottagecore", "dark academia", "clean girl", "mob wife",
    "quiet luxury", "old money", "soft life", "tradwife",
    "digital nomad", "van life", "side hustle", "hustle culture",
    "anti-work", "slow living", "minimalism", "maximalism",
    "y2k", "indie sleaze", "normcore", "gorpcore", "coastal grandmother",
    "coquette", "balletcore", "tenniscore", "barbiecore",
]

_GENERATION_AGE_RANGES: dict[str, tuple[int, int]] = {
    "gen_z": (12, 28),
    "millennial": (29, 44),
    "gen_x": (45, 60),
    "boomer": (61, 79),
}


class GenerationalPreferenceTracker(BaseSkill):
    """Track generational preferences and emerging behaviors."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-04",
        name="generational_preference_tracker",
        description="Track generational behaviors and brand expectations",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: Any, cb_tavily: Any = None) -> None:
        self._tavily = tavily_client
        self._cb_tavily = cb_tavily

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()
        industry = input_data.get("industry", "")
        persona_age_ranges = input_data.get("persona_age_ranges", [])
        generations = input_data.get(
            "generations", ["gen_z", "millennial", "gen_x", "boomer"]
        )

        generational_insights: list[dict[str, Any]] = []

        for gen in generations:
            gen_label = gen.replace("_", " ").title()
            query = (
                f"{gen_label} consumer behavior {industry} "
                f"brand preferences platform usage 2025 2026"
            )
            try:
                if self._cb_tavily:
                    results = await self._cb_tavily.call(
                        self._tavily.search, query, max_results=5
                    )
                else:
                    results = await self._tavily.search(query, max_results=5)

                profile: dict[str, Any] = {
                    "generation": gen_label,
                    "emerging_behaviors": [],
                    "language_patterns": [],
                    "platform_shifts": [],
                    "brand_expectations": [],
                    "subcultures": [],
                    "relevance_to_personas": [],
                }

                for r in results:
                    content = r.get("content", "")
                    content_lower = content.lower()
                    if not content:
                        continue

                    # Emerging behaviors: extract behavior-related snippets
                    profile["emerging_behaviors"].append(content[:200])

                    # Language patterns
                    for pattern in _LANGUAGE_MARKERS.get(gen, []):
                        if (
                            pattern in content_lower
                            and pattern not in profile["language_patterns"]
                        ):
                            profile["language_patterns"].append(pattern)

                    # Platform shifts
                    for platform in _PLATFORM_KEYWORDS:
                        if (
                            platform in content_lower
                            and platform not in profile["platform_shifts"]
                        ):
                            profile["platform_shifts"].append(platform)

                    # Brand expectations
                    for expect in _BRAND_EXPECTATION_KEYWORDS:
                        if (
                            expect in content_lower
                            and expect not in profile["brand_expectations"]
                        ):
                            profile["brand_expectations"].append(expect)

                    # Subcultures
                    for sub in _SUBCULTURE_KEYWORDS:
                        if (
                            sub in content_lower
                            and sub not in profile["subcultures"]
                        ):
                            profile["subcultures"].append(sub)

                # Relevance to personas (cross-reference age ranges)
                if persona_age_ranges:
                    gen_range = _GENERATION_AGE_RANGES.get(gen)
                    if gen_range:
                        for age_range in persona_age_ranges:
                            if self._age_ranges_overlap(gen_range, age_range):
                                profile["relevance_to_personas"].append(
                                    f"Overlaps with persona age range {age_range}"
                                )

                generational_insights.append(profile)
            except Exception as exc:
                logger.warning("Generational scan failed for %s: %s", gen, exc)

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"generational_insights": generational_insights},
            duration_ms=elapsed,
        )

    @staticmethod
    def _age_ranges_overlap(
        gen_range: tuple[int, int], persona_range: str
    ) -> bool:
        """Check if a generation's age range overlaps with a persona age range string."""
        try:
            parts = persona_range.replace("+", "-999").split("-")
            p_low = int(parts[0].strip())
            p_high = int(parts[1].strip()) if len(parts) > 1 else p_low + 10
            return gen_range[0] <= p_high and p_low <= gen_range[1]
        except (ValueError, IndexError):
            return False
