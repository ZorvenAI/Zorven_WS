"""SKL-BSA-10: Build Claude prompt section for story style guide."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class StoryStyleGuideBuilder:
    """Builds prompt sections for story style guide generation."""

    def build_prompt_section(
        self,
        context: dict[str, Any],
        origin_story: dict[str, Any],
        mission_vision: dict[str, Any],
    ) -> str:
        """Build prompt section for story style guide."""
        bpv = context.get("bpv", {})
        archetype = bpv.get("archetype", "")
        voice_matrix = bpv.get("voice_matrix", {})
        brand_values = bpv.get("brand_values", [])

        parts = [
            "Generate a comprehensive story style guide that ensures "
            "narrative consistency across all brand communications.\n",
        ]

        if archetype:
            parts.append(f"Brand archetype: {archetype}")
        if voice_matrix:
            parts.append(f"Voice matrix: {json.dumps(voice_matrix)}")
        if brand_values:
            parts.append(f"Brand values: {json.dumps(brand_values)}")

        parts.append(
            "\nThe style guide must include:\n"
            "1. narrative_principles: 5-7 rules for brand storytelling\n"
            "2. approved_themes: Themes that reinforce the brand narrative\n"
            "3. forbidden_themes: Themes to avoid (competitive/off-brand)\n"
            "4. tone_guidelines: Channel-specific tone adjustments\n"
            "5. example_passages: 3 short example passages showing the brand voice\n"
            "6. do_say / dont_say: Specific language guidance\n\n"
            "Output as 'story_style_guide' object."
        )

        return "\n".join(parts)
