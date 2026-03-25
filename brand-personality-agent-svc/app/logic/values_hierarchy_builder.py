"""SKL-BPV-07: Validate values hierarchy tiers."""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class ValuesHierarchyBuilder:
    """Validate values tiers (3-5 core, 3-5 supporting, 1-3 aspirational)."""

    async def validate(self, hierarchy: dict[str, Any]) -> dict[str, Any]:
        """Validate and trim values hierarchy to configured limits."""
        core = hierarchy.get("core", [])[:settings.MAX_CORE_VALUES]
        supporting = hierarchy.get("supporting", [])[:settings.MAX_SUPPORTING_VALUES]
        aspirational = hierarchy.get("aspirational", [])[:settings.MAX_ASPIRATIONAL_VALUES]

        authenticity = min(
            max(float(hierarchy.get("authenticity_score", 0)), 0), 100
        )

        return {
            "core": core,
            "supporting": supporting,
            "aspirational": aspirational,
            "authenticity_score": authenticity,
        }
