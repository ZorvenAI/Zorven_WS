"""SKL-BSA-02: Synthesize APA emotional drivers + VoCA language patterns."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AudienceEmotionalSynthesizer:
    """Synthesizes audience emotional data into narrative emotional arcs."""

    async def synthesize(
        self,
        apa_context: dict[str, Any],
        voca_context: dict[str, Any],
        bpv_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build emotional arc from APA + VoCA + BPV data."""
        emotional_drivers = apa_context.get("emotional_drivers", [])
        pain_points = apa_context.get("pain_points", [])
        aspirations = apa_context.get("aspirations", [])
        language_patterns = voca_context.get("language_patterns", [])
        sentiment = voca_context.get("sentiment_summary", {})
        raw_archetype = bpv_context.get("archetype", "")
        if isinstance(raw_archetype, dict):
            primary = raw_archetype.get("primary", "")
            archetype = primary.get("name", str(primary)) if isinstance(primary, dict) else str(primary)
        else:
            archetype = str(raw_archetype)
        values = bpv_context.get("brand_values", [])

        # Build emotional arc: tension → transformation → resolution
        arc = {
            "tension": {
                "pain_points": pain_points[:5],
                "negative_emotions": [
                    d for d in emotional_drivers
                    if isinstance(d, dict) and d.get("valence") == "negative"
                ][:3],
                "customer_language": [
                    p for p in language_patterns
                    if isinstance(p, dict) and p.get("context") == "frustration"
                ][:3],
            },
            "transformation": {
                "brand_promise": _archetype_promise(archetype),
                "values_bridge": values[:5],
                "emotional_shift": [
                    d for d in emotional_drivers
                    if isinstance(d, dict) and d.get("valence") == "positive"
                ][:3],
            },
            "resolution": {
                "aspirations": aspirations[:5],
                "success_language": [
                    p for p in language_patterns
                    if isinstance(p, dict) and p.get("context") == "satisfaction"
                ][:3],
                "sentiment_target": sentiment.get("target_sentiment", "positive"),
            },
        }

        logger.info(
            "Emotional arc built: %d tensions, %d aspirations",
            len(arc["tension"]["pain_points"]),
            len(arc["resolution"]["aspirations"]),
        )
        return arc


def _archetype_promise(archetype: str) -> str:
    """Map brand archetype to core narrative promise."""
    promises = {
        "hero": "Empowerment through courage and mastery",
        "sage": "Wisdom and understanding that illuminates truth",
        "explorer": "Freedom to discover your own path",
        "creator": "Innovation that brings visions to life",
        "ruler": "Control and order that creates stability",
        "magician": "Transformation that makes dreams reality",
        "lover": "Connection and intimacy that enriches life",
        "caregiver": "Nurturing protection that keeps you safe",
        "jester": "Joy and playfulness that lightens life",
        "everyman": "Belonging and authenticity for everyone",
        "innocent": "Simplicity and optimism for a better world",
        "outlaw": "Liberation from constraints and conventions",
    }
    return promises.get(archetype.lower(), "A promise of meaningful change")
