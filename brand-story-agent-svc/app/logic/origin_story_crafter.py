"""SKL-BSA-06: Build Claude prompt for origin story (3 versions)."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class OriginStoryCrafter:
    """Builds Claude prompts for origin story generation."""

    def build_system_prompt(self) -> str:
        """Build system prompt for narrative generation (Claude call 1)."""
        return (
            "You are a world-class brand storyteller and narrative strategist. "
            "You craft emotionally resonant brand stories that connect deeply with "
            "audiences while maintaining strategic alignment with positioning, "
            "personality, and naming decisions.\n\n"
            "You MUST respond with valid JSON only — no markdown, no commentary.\n\n"
            "Your output must include:\n"
            "1. origin_story: An object with 'versions' array containing 3 story "
            "versions (short ~500 words, medium ~800 words, long ~1500 words). "
            "Each version has: length_label, word_count_target, content, "
            "archetype_arc_alignment (0-1), emotional_resonance_score (0-1), "
            "voice_consistency_score (0-1).\n"
            "2. mission_vision: An object with 'mission' (string), 'mission_scores' "
            "(clarity, positioning_alignment, memorability — each 0-1), 'vision' (string), "
            "'vision_scores' (inspiration, ambition, achievability — each 0-1), "
            "'existing_mission' (from input if available), 'existing_vision', "
            "'refinement_notes'.\n"
            "3. pitches: An object with 'pitch_15s' (37 words), 'pitch_30s' (75 words), "
            "'pitch_60s' (150 words). Each has: duration_label, word_count, content, "
            "memorability_score (0-1), positioning_alignment (0-1).\n"
            "4. findings: Array of insight strings discovered during analysis.\n"
            "5. recommendations: Array of actionable recommendation strings.\n"
            "6. sources: Array of source objects (label, description).\n"
            "7. confidence_score: Float 0-1 indicating overall confidence.\n\n"
            "The origin story MUST follow the archetype's narrative arc. "
            "Use the brand's actual name, values, and positioning throughout. "
            "Write in the brand's established voice and tone."
        )

    def build_user_prompt(
        self,
        prompt: str,
        context: dict[str, Any],
        wf2_strategy: dict[str, Any],
        audience_emotional: dict[str, Any],
        existing_narrative: dict[str, Any],
        competitor_narrative: dict[str, Any],
    ) -> str:
        """Build user prompt for origin story generation."""
        company = context.get("company", {})
        bpa = context.get("bpa", {})
        bpv = context.get("bpv", {})
        nta = context.get("nta", {})

        sections = [
            f"## USER REQUEST\n{prompt}",
            f"## COMPANY\nName: {company.get('name', 'Unknown')}\n"
            f"Industry: {company.get('industry', '')}\n"
            f"Description: {company.get('description', '')}",
        ]

        # Positioning
        positioning = wf2_strategy.get("positioning", {})
        if positioning:
            sections.append(
                f"## BRAND POSITIONING\n"
                f"Statement: {positioning.get('positioning_statement', '')}\n"
                f"Value Prop: {positioning.get('value_proposition', '')}\n"
                f"Differentiators: {json.dumps(positioning.get('differentiators', []))}"
            )

        # Personality
        personality = wf2_strategy.get("personality", {})
        if personality:
            sections.append(
                f"## BRAND PERSONALITY\n"
                f"Archetype: {personality.get('archetype', '')}\n"
                f"Values: {json.dumps(personality.get('brand_values', []))}\n"
                f"Voice: {json.dumps(personality.get('voice_matrix', {}))}"
            )

        # Naming
        naming = wf2_strategy.get("naming", {})
        if naming:
            sections.append(
                f"## BRAND NAME & TAGLINE\n"
                f"Name: {naming.get('recommended_name', '')}\n"
                f"Tagline: {naming.get('recommended_tagline', '')}"
            )

        # Existing narrative elements
        if existing_narrative:
            sections.append(
                f"## EXISTING NARRATIVE ELEMENTS\n"
                f"Has founding story: {existing_narrative.get('has_founding_story', False)}\n"
                f"Founding story: {existing_narrative.get('existing_narrative', {}).get('founding_story', '')}\n"
                f"Existing mission: {existing_narrative.get('existing_narrative', {}).get('mission', '')}\n"
                f"Existing vision: {existing_narrative.get('existing_narrative', {}).get('vision', '')}\n"
                f"Gaps: {json.dumps(existing_narrative.get('gaps', []))}"
            )

        # Emotional arc
        if audience_emotional:
            sections.append(
                f"## AUDIENCE EMOTIONAL ARC\n"
                f"{json.dumps(audience_emotional, default=str)[:2000]}"
            )

        # Competitive landscape
        if competitor_narrative:
            sections.append(
                f"## COMPETITIVE NARRATIVE LANDSCAPE\n"
                f"White space archetypes: {json.dumps(competitor_narrative.get('archetype_white_space', []))}\n"
                f"Opportunities: {json.dumps(competitor_narrative.get('narrative_opportunities', []))}"
            )

        return "\n\n".join(sections)
