"""SKL-BSA-05: CIA competitor story archetypes → narrative white space."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CompetitorNarrativeMapper:
    """Maps competitor narratives to identify storytelling white space."""

    async def map(self, cia_context: dict[str, Any]) -> dict[str, Any]:
        """Analyze competitor narratives and find white space opportunities."""
        competitors = cia_context.get("competitors", [])

        competitor_archetypes = []
        narrative_themes_used = set()

        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            name = comp.get("name", comp.get("company_name", ""))
            archetype = self._detect_archetype(comp)
            themes = self._extract_themes(comp)
            narrative_themes_used.update(themes)

            competitor_archetypes.append(
                {
                    "competitor": name,
                    "archetype": archetype,
                    "narrative_themes": themes,
                    "messaging_tone": comp.get("messaging_tone", ""),
                    "tagline": comp.get("tagline", ""),
                }
            )

        # Identify white space (archetypes/themes NOT used by competitors)
        all_archetypes = {
            "hero",
            "sage",
            "explorer",
            "creator",
            "ruler",
            "magician",
            "lover",
            "caregiver",
            "jester",
            "everyman",
            "innocent",
            "outlaw",
        }
        used_archetypes = {
            c["archetype"].lower() for c in competitor_archetypes if c["archetype"]
        }
        available_archetypes = all_archetypes - used_archetypes

        result = {
            "competitor_archetypes": competitor_archetypes[:10],
            "themes_in_use": list(narrative_themes_used)[:15],
            "archetype_white_space": list(available_archetypes),
            "narrative_opportunities": self._identify_opportunities(
                competitor_archetypes, narrative_themes_used
            ),
        }

        logger.info(
            "Competitor mapping: %d competitors, %d archetype white spaces",
            len(competitor_archetypes),
            len(available_archetypes),
        )
        return result

    def _detect_archetype(self, competitor: dict) -> str:
        """Detect narrative archetype from competitor messaging."""
        messaging = (
            competitor.get("messaging_tone", "")
            + " "
            + competitor.get("tagline", "")
            + " "
            + competitor.get("description", "")
        ).lower()

        archetype_signals = {
            "hero": ["empower", "strength", "achieve", "overcome", "bold"],
            "sage": ["wisdom", "knowledge", "insight", "understand", "learn"],
            "explorer": ["discover", "journey", "freedom", "adventure", "pioneer"],
            "creator": ["innovate", "create", "design", "imagine", "build"],
            "ruler": ["lead", "premium", "best", "elite", "authority"],
            "magician": ["transform", "magic", "vision", "dream", "change"],
        }

        best_match = ""
        best_score = 0
        for archetype, signals in archetype_signals.items():
            score = sum(1 for s in signals if s in messaging)
            if score > best_score:
                best_score = score
                best_match = archetype

        return best_match if best_score > 0 else ""

    def _extract_themes(self, competitor: dict) -> list[str]:
        """Extract narrative themes from competitor data."""
        themes = []
        description = (
            competitor.get("description", "") + " " + competitor.get("tagline", "")
        ).lower()

        theme_keywords = {
            "innovation": ["innovat", "cutting-edge", "breakthrough"],
            "sustainability": ["sustain", "green", "eco", "planet"],
            "community": ["community", "together", "belong"],
            "empowerment": ["empower", "enable", "unlock"],
            "simplicity": ["simple", "easy", "effortless"],
            "trust": ["trust", "reliable", "depend"],
            "premium": ["premium", "luxury", "exclusive"],
        }

        for theme, keywords in theme_keywords.items():
            if any(kw in description for kw in keywords):
                themes.append(theme)

        return themes

    def _identify_opportunities(
        self, competitors: list[dict], themes_used: set
    ) -> list[str]:
        """Identify narrative opportunities based on gaps."""
        opportunities = []

        all_themes = {
            "innovation",
            "sustainability",
            "community",
            "empowerment",
            "simplicity",
            "trust",
            "premium",
            "authenticity",
            "heritage",
            "purpose",
            "transformation",
        }
        unused = all_themes - themes_used
        if unused:
            opportunities.append(
                f"Unexploited narrative themes: {', '.join(list(unused)[:5])}"
            )

        if len(competitors) > 3:
            archetypes = [c["archetype"] for c in competitors if c["archetype"]]
            if archetypes:
                from collections import Counter

                most_common = Counter(archetypes).most_common(1)[0]
                opportunities.append(
                    f"Most competitors use '{most_common[0]}' archetype — "
                    f"consider differentiation"
                )

        return opportunities
