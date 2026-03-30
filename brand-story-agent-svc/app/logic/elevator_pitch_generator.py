"""SKL-BSA-08: Build Claude prompt section for elevator pitches."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Word count targets at 150 wpm speaking rate
PITCH_SPECS = {
    "pitch_15s": {"duration": "15s", "words": 37, "label": "15-second"},
    "pitch_30s": {"duration": "30s", "words": 75, "label": "30-second"},
    "pitch_60s": {"duration": "60s", "words": 150, "label": "60-second"},
}


class ElevatorPitchGenerator:
    """Builds prompt sections for elevator pitch generation."""

    def build_prompt_section(
        self,
        context: dict[str, Any],
        wf2_strategy: dict[str, Any],
    ) -> str:
        """Build prompt section for elevator pitches."""
        company = context.get("company", {})
        naming = wf2_strategy.get("naming", {})
        positioning = wf2_strategy.get("positioning", {})

        brand_name = naming.get("recommended_name", company.get("name", "the brand"))
        tagline = naming.get("recommended_tagline", "")
        value_prop = positioning.get("value_proposition", "")

        parts = [
            "## ELEVATOR PITCHES",
            f"Brand name: {brand_name}",
        ]

        if tagline:
            parts.append(f"Tagline: {tagline}")
        if value_prop:
            parts.append(f"Value proposition: {value_prop}")

        parts.append(
            "\nGenerate 3 elevator pitches at different durations "
            "(150 words per minute speaking rate):"
        )

        for key, spec in PITCH_SPECS.items():
            parts.append(
                f"- {key}: {spec['label']} pitch (~{spec['words']} words). "
                f"Must be self-contained and compelling at this length."
            )

        parts.append(
            "\nEach pitch must:\n"
            "- Open with a hook\n"
            "- Include the brand name naturally\n"
            "- Convey the core value proposition\n"
            "- End with a memorable close\n"
            "- Score for memorability (0-1) and positioning_alignment (0-1)"
        )

        return "\n".join(parts)
