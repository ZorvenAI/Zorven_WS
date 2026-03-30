"""SKL-BSA-11: Sub-brand story variation (if BAA + brand_context_id)."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SubBrandStoryVariation:
    """Generates story variations for sub-brands from BAA hierarchy."""

    def build_prompt_section(
        self,
        baa_context: dict[str, Any],
        origin_story: dict[str, Any],
    ) -> str:
        """Build prompt section for sub-brand story variations."""
        if not baa_context:
            return (
                "No brand architecture data available. "
                "Skip sub-brand story generation. "
                "Output empty 'subbrand_stories' array."
            )

        hierarchy = baa_context.get("hierarchy", {})
        sub_brands = baa_context.get("sub_brands", [])

        if not sub_brands and not hierarchy:
            return (
                "Single-brand architecture (no sub-brands). "
                "Output empty 'subbrand_stories' array."
            )

        parts = [
            "Generate story variations for each sub-brand in the hierarchy. "
            "Each sub-brand story should:\n"
            "- Inherit the parent brand's narrative DNA\n"
            "- Have its own unique positioning hook\n"
            "- Clearly state relationship to parent brand\n\n"
            "Sub-brands:\n"
        ]

        for sb in sub_brands[:5]:
            if isinstance(sb, dict):
                parts.append(
                    f"- {sb.get('name', 'Unknown')}: "
                    f"scope={sb.get('brand_scope', '')}, "
                    f"relationship={sb.get('relationship_to_parent', '')}, "
                    f"target={sb.get('target_persona', '')}"
                )

        if hierarchy:
            parts.append(f"\nFull hierarchy: {json.dumps(hierarchy, default=str)[:1500]}")

        parts.append(
            "\nFor each sub-brand, output: brand_context_id, brand_name, "
            "origin_story_short (~100 words), positioning_hook (1 sentence), "
            "relationship_to_parent (how it connects to parent story)."
        )

        return "\n".join(parts)
