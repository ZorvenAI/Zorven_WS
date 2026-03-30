"""SKL-BSA-12: Capstone — assemble all artifacts into final narrative package."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrandNarrativeSynthesizer:
    """Builds the synthesis prompt for Claude call 2 (narrative package assembly)."""

    def build_system_prompt(self) -> str:
        """Build system prompt for narrative synthesis (Claude call 2)."""
        return (
            "You are a brand narrative architect assembling the final brand "
            "story package. You adapt a core brand narrative into channel-specific "
            "versions, create a storytelling style guide, and generate sub-brand "
            "story variations.\n\n"
            "You MUST respond with valid JSON only — no markdown, no commentary.\n\n"
            "Your output must include:\n"
            "1. channel_narratives: Object with keys website_about, social_bio, "
            "investor, press_boilerplate. Each has: channel, content, tone, "
            "word_count. Include 'channel_consistency_score' (0-1).\n"
            "2. story_style_guide: Object with narrative_principles (array), "
            "approved_themes (array), forbidden_themes (array), "
            "tone_guidelines (object), "
            "story_examples (array of {context, example}).\n"
            "3. subbrand_stories: Array of objects with brand_context_id, "
            "sub_brand, narrative_snippet, positioning_hook, "
            "relationship_to_parent. Empty array if no sub-brands.\n"
            "4. narrative_package: Object summarizing the complete narrative "
            "with: brand_name, archetype, narrative_arc, "
            "overall_confidence (0-1), positioning_narrative_alignment (0-1), "
            "voice_consistency (0-1), key_themes (array), "
            "narrative_dna (core story essence in 1 sentence).\n"
            "5. wf2_strategy_summary: Object summarizing the complete WF2 "
            "strategy with: positioning_summary, architecture_summary, "
            "personality_summary, naming_summary, story_summary, "
            "strategic_coherence_score (0-1).\n"
            "6. findings: Array of insight strings.\n"
            "7. recommendations: Array of actionable recommendation strings.\n"
            "8. confidence_score: Float 0-1."
        )
