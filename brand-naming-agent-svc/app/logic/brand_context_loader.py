"""SKL-NTA-01: Load brand context from BAA hierarchy for sub-brand naming."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrandContextLoader:
    """Load brand architecture context for naming constraints."""

    async def load(
        self,
        baa_data: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract architecture constraints for naming."""
        config = config or {}
        brand_context_id = config.get("brand_context_id", "parent")

        architecture_model = ""
        hierarchy_depth = 0
        parent_brand_name = ""
        naming_constraints = []

        if baa_data:
            rec = baa_data.get("recommendation", {})
            if isinstance(rec, dict):
                architecture_model = rec.get("recommended_model", "")
            hierarchy = baa_data.get("hierarchy", {})
            if isinstance(hierarchy, dict):
                hierarchy_depth = hierarchy.get("total_depth", 0)
            parent_brand_name = baa_data.get("parent_brand_name", "")

            # Extract naming constraints based on architecture model
            if architecture_model == "branded_house":
                naming_constraints.append(
                    "Names must clearly extend the parent brand"
                )
            elif architecture_model == "house_of_brands":
                naming_constraints.append(
                    "Names should be distinct and independently memorable"
                )
            elif architecture_model == "endorsed":
                naming_constraints.append(
                    "Names should work with parent brand endorsement"
                )

        return {
            "brand_context_id": brand_context_id,
            "architecture_model": architecture_model,
            "hierarchy_depth": hierarchy_depth,
            "parent_brand_name": parent_brand_name,
            "naming_constraints": naming_constraints,
            "has_architecture": bool(baa_data),
        }
