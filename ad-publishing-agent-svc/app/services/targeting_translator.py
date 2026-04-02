"""Persona-to-Meta targeting spec translator.

Uses Claude Sonnet 4 to intelligently map human-readable persona
attributes (demographics, interests, behaviors) to Meta's targeting
API format. Handles Special Ad Category restrictions.
"""

import logging
from typing import Any

from app.services.anthropic_client import AnthropicClient

logger = logging.getLogger(__name__)

TARGETING_SYSTEM_PROMPT = """You are a Meta Ads targeting specialist. Your job is to
translate audience persona descriptions into Meta Marketing API targeting specs.

Output ONLY valid JSON matching this schema:
{
  "geo_locations": {"countries": ["US"], "regions": [], "cities": []},
  "age_min": 18,
  "age_max": 65,
  "genders": [1, 2],
  "interests": [{"id": "6003139266461", "name": "Technology"}],
  "behaviors": [],
  "flex_spec": [],
  "publisher_platforms": ["facebook", "instagram"],
  "facebook_positions": ["feed"],
  "instagram_positions": ["stream"]
}

Rules:
- genders: 1=male, 2=female. Use [1,2] for all genders.
- age_min must be >= 18, age_max <= 65.
- interests and behaviors use Meta targeting search IDs.
  Map the persona's interests to the closest Meta interest categories.
  Use realistic Meta interest IDs where possible; if unsure, use the
  interest name and mark with "estimated": true.
- If special_ad_categories includes HOUSING, CREDIT, or EMPLOYMENT:
  DO NOT include age_min, age_max, genders, or zip code targeting.
  Only use geo_locations at country/region level.
"""


class TargetingTranslator:
    """Translates persona profiles into Meta Ads targeting specs."""

    def __init__(self, llm_client: AnthropicClient | None = None):
        self._llm = llm_client

    async def translate(
        self,
        persona: dict[str, Any],
        industry: str = "",
        special_ad_categories: list[str] | None = None,
        placements: list[str] | None = None,
    ) -> dict[str, Any]:
        """Translate a single persona into a Meta targeting spec.

        Parameters
        ----------
        persona : dict
            Persona with demographics, interests, behaviors keys.
        industry : str
            Company industry for context.
        special_ad_categories : list
            Meta Special Ad Categories (limits targeting options).
        placements : list
            Requested ad placements.

        Returns
        -------
        dict with targeting spec + estimated_reach + warnings.
        """
        categories = special_ad_categories or []

        if self._llm is None:
            targeting = self._fallback_translation(
                persona, categories, placements
            )
        else:
            user_prompt = self._build_prompt(
                persona, industry, categories, placements
            )
            try:
                targeting = await self._llm.generate_json(
                    system_prompt=TARGETING_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.2,
                )
            except Exception as exc:
                logger.warning(
                    "LLM targeting translation failed, using fallback: %s",
                    exc,
                )
                targeting = self._fallback_translation(
                    persona, categories, placements
                )

        # Enforce Special Ad Category restrictions
        if categories:
            targeting = self._apply_category_restrictions(
                targeting, categories
            )

        # Validate minimum fields
        warnings = self._validate_targeting(targeting)

        return {
            "targeting_spec": targeting,
            "persona_name": persona.get("name", "Unknown"),
            "estimated_reach": targeting.pop("estimated_reach", 0),
            "warnings": warnings,
        }

    async def translate_all(
        self,
        personas: list[dict[str, Any]],
        industry: str = "",
        special_ad_categories: list[str] | None = None,
        placements: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Translate multiple personas into targeting specs."""
        results = []
        for persona in personas:
            result = await self.translate(
                persona, industry, special_ad_categories, placements
            )
            results.append(result)
        return results

    def _build_prompt(
        self,
        persona: dict[str, Any],
        industry: str,
        categories: list[str],
        placements: list[str] | None,
    ) -> str:
        import json

        parts = [
            f"Industry: {industry}" if industry else "",
            f"Special Ad Categories: {', '.join(categories)}"
            if categories
            else "",
            f"Requested placements: {', '.join(placements)}"
            if placements
            else "",
            f"Persona:\n{json.dumps(persona, indent=2)}",
        ]
        return "\n\n".join(p for p in parts if p)

    @staticmethod
    def _fallback_translation(
        persona: dict[str, Any],
        categories: list[str],
        placements: list[str] | None,
    ) -> dict[str, Any]:
        """Rule-based fallback when LLM is unavailable."""
        demographics = persona.get("demographics", {})

        targeting: dict[str, Any] = {
            "geo_locations": {
                "countries": demographics.get("countries", ["US"]),
            },
            "interests": [],
            "behaviors": [],
        }

        # Demographics (skip if Special Ad Category)
        if not categories:
            targeting["age_min"] = demographics.get("age_min", 18)
            targeting["age_max"] = demographics.get("age_max", 65)
            gender_map = {"male": 1, "female": 2}
            genders = demographics.get("genders", [])
            if genders:
                targeting["genders"] = [
                    gender_map.get(g.lower(), 0) for g in genders if g
                ]

        # Map interests as estimated
        for interest in persona.get("interests", []):
            name = interest if isinstance(interest, str) else interest.get(
                "name", str(interest)
            )
            targeting["interests"].append(
                {"name": name, "estimated": True}
            )

        # Placements
        if placements:
            platforms = set()
            positions: dict[str, list[str]] = {}
            placement_map = {
                "FACEBOOK_FEED": ("facebook", "feed"),
                "INSTAGRAM_FEED": ("instagram", "stream"),
                "INSTAGRAM_STORIES": ("instagram", "story"),
                "AUDIENCE_NETWORK": ("audience_network", "classic"),
            }
            for p in placements:
                if p in placement_map:
                    platform, position = placement_map[p]
                    platforms.add(platform)
                    positions.setdefault(
                        f"{platform}_positions", []
                    ).append(position)
            if platforms:
                targeting["publisher_platforms"] = sorted(platforms)
            targeting.update(positions)

        return targeting

    @staticmethod
    def _apply_category_restrictions(
        targeting: dict[str, Any],
        categories: list[str],
    ) -> dict[str, Any]:
        """Remove restricted targeting for Special Ad Categories."""
        restricted = {"HOUSING", "CREDIT", "EMPLOYMENT"}
        if set(categories) & restricted:
            targeting.pop("age_min", None)
            targeting.pop("age_max", None)
            targeting.pop("genders", None)
            # Restrict geo to country/region level only
            geo = targeting.get("geo_locations", {})
            geo.pop("cities", None)
            geo.pop("zips", None)
        return targeting

    @staticmethod
    def _validate_targeting(targeting: dict[str, Any]) -> list[str]:
        """Validate targeting spec and return warnings."""
        warnings = []
        geo = targeting.get("geo_locations", {})
        if not geo.get("countries") and not geo.get("regions"):
            warnings.append("No geo targeting specified")
        if not targeting.get("interests") and not targeting.get("behaviors"):
            warnings.append(
                "No interest or behavior targeting — audience may be "
                "too broad"
            )
        return warnings
