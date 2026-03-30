"""SKL-BSA-07: Build Claude prompt section for mission/vision."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MissionVisionRefiner:
    """Builds prompt sections for mission/vision generation or refinement."""

    def build_prompt_section(
        self,
        context: dict[str, Any],
        wf2_strategy: dict[str, Any],
    ) -> str:
        """Build prompt section for mission/vision."""
        company = context.get("company", {})
        existing_mission = company.get("mission", "")
        existing_vision = company.get("vision", "")
        positioning = wf2_strategy.get("positioning", {})
        personality = wf2_strategy.get("personality", {})

        parts = ["## MISSION & VISION GENERATION"]

        if existing_mission:
            parts.append(
                f"Existing mission: \"{existing_mission}\"\n"
                f"Refine this mission to align with the new positioning. "
                f"Preserve the core intent while strengthening strategic alignment."
            )
        else:
            parts.append(
                "No existing mission statement. Generate a fresh mission that:\n"
                "- Articulates the brand's core purpose\n"
                "- Aligns with the positioning statement\n"
                "- Resonates with the target audience\n"
                "- Is concise (1-2 sentences)"
            )

        if existing_vision:
            parts.append(
                f"Existing vision: \"{existing_vision}\"\n"
                f"Refine to align with strategic direction."
            )
        else:
            parts.append(
                "No existing vision statement. Generate a vision that:\n"
                "- Describes the aspirational future state\n"
                "- Inspires stakeholders\n"
                "- Is ambitious yet achievable\n"
                "- Is concise (1-2 sentences)"
            )

        if positioning.get("positioning_statement"):
            parts.append(
                f"Positioning alignment: {positioning['positioning_statement']}"
            )

        if personality.get("brand_values"):
            parts.append(
                f"Brand values to reflect: {json.dumps(personality['brand_values'])}"
            )

        return "\n".join(parts)
