"""SKL-BSA-04: Analyze Company model seeds vs BPA/BPV alignment → gap analysis."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ExistingNarrativeAnalyzer:
    """Analyzes existing company narrative elements against strategic positioning."""

    async def analyze(
        self,
        company_context: dict[str, Any],
        bpa_context: dict[str, Any],
        bpv_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Identify gaps between existing narrative and strategic direction."""
        existing = {
            "mission": company_context.get("mission", ""),
            "vision": company_context.get("vision", ""),
            "founding_story": company_context.get("founding_story", ""),
            "description": company_context.get("description", ""),
            "values": company_context.get("values", []),
        }

        target_positioning = bpa_context.get("positioning_statement", "")
        target_archetype = bpv_context.get("archetype", "")
        target_values = bpv_context.get("brand_values", [])

        gaps = []
        alignments = []

        # Mission alignment check
        if existing["mission"] and target_positioning:
            gaps.append({
                "element": "mission",
                "existing": existing["mission"],
                "target": target_positioning,
                "action": "refine",
                "note": "Evaluate mission alignment with new positioning",
            })
        elif not existing["mission"]:
            gaps.append({
                "element": "mission",
                "existing": "",
                "target": target_positioning,
                "action": "create",
                "note": "No existing mission — generate fresh from positioning",
            })

        # Vision gap
        if not existing["vision"]:
            gaps.append({
                "element": "vision",
                "existing": "",
                "target": "",
                "action": "create",
                "note": "No existing vision statement",
            })

        # Founding story
        if existing["founding_story"]:
            alignments.append({
                "element": "founding_story",
                "note": "Existing founding story available for origin story crafting",
            })
        else:
            gaps.append({
                "element": "founding_story",
                "existing": "",
                "target": "",
                "action": "create",
                "note": "No founding story — will craft from company context",
            })

        # Values alignment
        existing_values = set(
            v.lower() if isinstance(v, str) else str(v).lower()
            for v in existing["values"]
        )
        target_values_set = set(
            v.lower() if isinstance(v, str) else str(v).lower()
            for v in target_values
        )
        if existing_values and target_values_set:
            overlap = existing_values & target_values_set
            if overlap:
                alignments.append({
                    "element": "values",
                    "note": f"Values alignment: {', '.join(overlap)}",
                })

        result = {
            "existing_narrative": existing,
            "gaps": gaps,
            "alignments": alignments,
            "has_founding_story": bool(existing["founding_story"]),
            "has_existing_mission": bool(existing["mission"]),
            "has_existing_vision": bool(existing["vision"]),
            "archetype_target": target_archetype,
        }

        logger.info(
            "Narrative analysis: %d gaps, %d alignments",
            len(gaps),
            len(alignments),
        )
        return result
