"""SKL-BPV-03: Map Company.brand_voice to Aaker seed weights + load BPA/BAA."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Brand voice → Aaker seed weights (from design doc §2.5)
BRAND_VOICE_AAKER_MAP: dict[str, dict[str, Any]] = {
    "professional": {
        "sincerity": 60, "excitement": 30, "competence": 85,
        "sophistication": 70, "ruggedness": 20,
        "archetypes": ["Sage", "Ruler"],
    },
    "friendly": {
        "sincerity": 85, "excitement": 60, "competence": 50,
        "sophistication": 40, "ruggedness": 30,
        "archetypes": ["Caregiver", "Regular Guy"],
    },
    "authoritative": {
        "sincerity": 40, "excitement": 25, "competence": 90,
        "sophistication": 75, "ruggedness": 45,
        "archetypes": ["Ruler", "Sage"],
    },
    "casual": {
        "sincerity": 70, "excitement": 75, "competence": 40,
        "sophistication": 30, "ruggedness": 50,
        "archetypes": ["Regular Guy", "Jester"],
    },
    "luxury": {
        "sincerity": 50, "excitement": 40, "competence": 70,
        "sophistication": 95, "ruggedness": 15,
        "archetypes": ["Ruler", "Lover"],
    },
    "bold": {
        "sincerity": 30, "excitement": 90, "competence": 55,
        "sophistication": 50, "ruggedness": 75,
        "archetypes": ["Hero", "Outlaw"],
    },
    "empathetic": {
        "sincerity": 90, "excitement": 35, "competence": 55,
        "sophistication": 60, "ruggedness": 20,
        "archetypes": ["Caregiver", "Innocent"],
    },
    "innovative": {
        "sincerity": 45, "excitement": 85, "competence": 80,
        "sophistication": 65, "ruggedness": 35,
        "archetypes": ["Magician", "Creator"],
    },
}


class IdentityValuesSeedLoader:
    """Load identity seed from Company brand_voice + BPA + BAA."""

    async def load(
        self,
        company_data: dict[str, Any],
        bpa_data: dict[str, Any],
        baa_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract identity seed for personality design."""
        brand_voice = (company_data.get("brand_voice", "") or "").lower().strip()
        values = company_data.get("values", "")
        vision = company_data.get("vision_statement", "")
        mission = company_data.get("mission_statement", "")

        # Map brand_voice to Aaker seed weights
        seed_weights = BRAND_VOICE_AAKER_MAP.get(brand_voice, {})
        suggested_archetypes = seed_weights.get("archetypes", [])

        # Extract positioning context
        positioning = bpa_data.get("recommended_positioning", {})
        differentiation = bpa_data.get("differentiation", {})

        # Extract architecture context (if available)
        architecture = {}
        if baa_data:
            architecture = {
                "model": baa_data.get("recommendation", {}).get(
                    "recommended_model", ""
                ),
                "hierarchy_depth": baa_data.get("hierarchy", {}).get(
                    "total_depth", 0
                ),
            }

        return {
            "brand_voice": brand_voice,
            "brand_voice_mapped": bool(seed_weights),
            "aaker_seed_weights": {
                k: v for k, v in seed_weights.items() if k != "archetypes"
            },
            "suggested_archetypes": suggested_archetypes,
            "company_values": values,
            "vision": vision,
            "mission": mission,
            "positioning": positioning,
            "differentiation": differentiation,
            "architecture": architecture,
        }
