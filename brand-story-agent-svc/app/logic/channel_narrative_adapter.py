"""SKL-BSA-09: Build Claude prompt section for channel-specific narratives."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

CHANNELS = [
    {
        "id": "website_about",
        "name": "Website About Page",
        "tone": "professional yet warm",
        "length": "200-400 words",
        "notes": "Include founding story elements, mission, and value proposition",
    },
    {
        "id": "social_bio",
        "name": "Social Media Bio",
        "tone": "concise and engaging",
        "length": "150-160 characters",
        "notes": "Twitter/X and LinkedIn compatible. Include tagline if possible",
    },
    {
        "id": "investor",
        "name": "Investor Narrative",
        "tone": "data-informed and visionary",
        "length": "300-500 words",
        "notes": "Emphasize market opportunity, traction, and vision. Business-focused",
    },
    {
        "id": "press",
        "name": "Press Boilerplate",
        "tone": "journalistic and factual",
        "length": "100-150 words",
        "notes": "Standard press release boilerplate. Third person. Factual",
    },
]


class ChannelNarrativeAdapter:
    """Builds prompt sections for channel-specific narrative adaptations."""

    def build_prompt_section(
        self,
        context: dict[str, Any],
        origin_story: dict[str, Any],
        mission_vision: dict[str, Any],
    ) -> str:
        """Build prompt section for channel narrative adaptation."""
        parts = [
            "Adapt the brand narrative for each channel below. "
            "Maintain voice consistency across all channels while adjusting "
            "tone, length, and emphasis for each audience.\n"
        ]

        for channel in CHANNELS:
            parts.append(
                f"### {channel['name']} ({channel['id']})\n"
                f"- Tone: {channel['tone']}\n"
                f"- Length: {channel['length']}\n"
                f"- Notes: {channel['notes']}\n"
            )

        parts.append(
            "Output 'channel_narratives' as an object with keys: "
            "website_about, social_bio, investor, press. "
            "Each has: channel, content, tone, word_count. "
            "Also include 'channel_consistency_score' (0-1) "
            "measuring voice consistency across all channels."
        )

        return "\n".join(parts)
