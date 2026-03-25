"""SKL-BPV-06: Validate Jungian archetype selection."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

VALID_ARCHETYPES = {
    "Innocent", "Sage", "Explorer", "Outlaw", "Magician", "Hero",
    "Lover", "Jester", "Regular Guy", "Caregiver", "Ruler", "Creator",
}


class ArchetypeSelector:
    """Validate archetype from 12 Jungian set."""

    async def validate(self, archetype: dict[str, Any]) -> dict[str, Any]:
        """Validate archetype selection."""
        primary = archetype.get("primary", {})
        secondary = archetype.get("secondary", {})

        # Validate archetype names
        primary_name = primary.get("name", "")
        if primary_name and primary_name not in VALID_ARCHETYPES:
            logger.warning("Unknown primary archetype: %s", primary_name)

        secondary_name = secondary.get("name", "")
        if secondary_name and secondary_name not in VALID_ARCHETYPES:
            logger.warning("Unknown secondary archetype: %s", secondary_name)

        resonance = min(max(float(archetype.get("resonance_score", 0)), 0), 100)

        return {
            "primary": primary,
            "secondary": secondary,
            "resonance_score": resonance,
            "blend_rationale": archetype.get("blend_rationale", ""),
        }
