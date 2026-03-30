"""SKL-NTA-04: Load identity/values from BPV for naming alignment."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class IdentitySeedLoader:
    """Load personality identity seed for name-personality alignment."""

    async def load(
        self,
        bpv_data: dict[str, Any],
        bpa_data: dict[str, Any],
        company_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract identity seed for naming design."""
        company_data = company_data or {}

        # BPV personality traits
        aaker_profile = bpv_data.get("aaker_profile", {})
        archetype = bpv_data.get("archetype", {})
        values_hierarchy = bpv_data.get("values_hierarchy", {})
        voice_matrix = bpv_data.get("voice_matrix", {})
        character_brief = bpv_data.get("character_brief", {})

        # Extract primary personality dimension
        primary_dimension = ""
        if isinstance(aaker_profile, dict):
            primary_dimension = aaker_profile.get("primary_dimension", "")

        # Primary archetype
        primary_archetype = ""
        if isinstance(archetype, dict):
            primary = archetype.get("primary", {})
            if isinstance(primary, dict):
                primary_archetype = primary.get("name", "")

        # Core values
        core_values = []
        if isinstance(values_hierarchy, dict):
            for v in values_hierarchy.get("core", []):
                if isinstance(v, dict):
                    core_values.append(v.get("name", ""))
                elif isinstance(v, str):
                    core_values.append(v)

        # Brand positioning
        positioning = bpa_data.get("recommended_positioning", {})
        differentiation = bpa_data.get("differentiation", {})

        # Company
        brand_voice = (company_data.get("brand_voice", "") or "").lower().strip()
        vision = company_data.get("vision_statement", "")
        mission = company_data.get("mission_statement", "")

        return {
            "primary_dimension": primary_dimension,
            "primary_archetype": primary_archetype,
            "core_values": core_values,
            "aaker_profile": aaker_profile,
            "voice_matrix": voice_matrix,
            "character_brief": character_brief,
            "positioning": positioning,
            "differentiation": differentiation,
            "brand_voice": brand_voice,
            "vision": vision,
            "mission": mission,
            "has_personality": bool(primary_dimension or primary_archetype),
        }
