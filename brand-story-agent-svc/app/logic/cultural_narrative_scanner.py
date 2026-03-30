"""SKL-BSA-03: TCIA cultural trends → narrative patterns (rising/fading)."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CulturalNarrativeScanner:
    """Maps cultural trends to narrative patterns for brand storytelling."""

    async def scan(self, tcia_context: dict[str, Any]) -> dict[str, Any]:
        """Scan TCIA trends and map to narrative relevance."""
        trends = tcia_context.get("trends", [])
        cultural_shifts = tcia_context.get("cultural_shifts", [])
        opportunity_alerts = tcia_context.get("opportunity_alerts", [])

        rising_narratives = []
        fading_narratives = []

        for trend in trends:
            if not isinstance(trend, dict):
                continue
            momentum = trend.get("momentum", 0)
            name = trend.get("name", trend.get("trend_name", ""))
            if not name:
                continue

            narrative_relevance = {
                "trend": name,
                "category": trend.get("category", ""),
                "narrative_angle": _suggest_narrative_angle(trend),
                "momentum": momentum,
            }

            if momentum > 0:
                rising_narratives.append(narrative_relevance)
            else:
                fading_narratives.append(narrative_relevance)

        # Sort by absolute momentum
        rising_narratives.sort(key=lambda x: x["momentum"], reverse=True)
        fading_narratives.sort(key=lambda x: abs(x["momentum"]), reverse=True)

        result = {
            "rising_narratives": rising_narratives[:5],
            "fading_narratives": fading_narratives[:3],
            "cultural_shifts": [
                {
                    "shift": s.get("description", str(s)) if isinstance(s, dict) else str(s),
                    "narrative_implication": "Adapt brand story to reflect this cultural shift",
                }
                for s in cultural_shifts[:3]
            ],
            "opportunity_alerts": [
                a.get("description", str(a)) if isinstance(a, dict) else str(a)
                for a in opportunity_alerts[:3]
            ],
        }

        logger.info(
            "Cultural scan: %d rising, %d fading narratives",
            len(result["rising_narratives"]),
            len(result["fading_narratives"]),
        )
        return result


def _suggest_narrative_angle(trend: dict) -> str:
    """Suggest how a trend could inform brand narrative."""
    category = trend.get("category", "").lower()
    if "sustainability" in category or "green" in category:
        return "Purpose-driven origin story emphasizing environmental responsibility"
    if "ai" in category or "tech" in category:
        return "Innovation narrative showcasing forward-thinking vision"
    if "wellness" in category or "health" in category:
        return "Care-centered story highlighting human wellbeing"
    if "community" in category or "social" in category:
        return "Belonging narrative centered on community building"
    return "Trend-aligned storytelling for cultural relevance"
