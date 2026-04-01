"""SKL-CGA-08: Primary Copy Generator.

Builds a prompt section for Claude call 2 that instructs Claude to
generate 2-3 primary copy variants per audience x funnel in short (125),
medium (250), and long (500+) lengths with funnel-specific messaging.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Copy length specifications
_COPY_LENGTHS: dict[str, dict[str, Any]] = {
    "short": {
        "max_chars": 125,
        "label": "Short (125 chars)",
        "use_case": "Feed ads, Reels overlays, quick-scroll placements",
    },
    "medium": {
        "max_chars": 250,
        "label": "Medium (250 chars)",
        "use_case": "Standard feed ads, Stories with read-more",
    },
    "long": {
        "max_chars": 500,
        "label": "Long (500+ chars)",
        "use_case": "Long-form feed, Marketplace, detailed storytelling",
    },
}

# Funnel stage -> copy strategy
_FUNNEL_COPY_STRATEGIES: dict[str, dict[str, str]] = {
    "tofu": {
        "approach": "aspirational, story-driven micro-narratives",
        "content_type": (
            "Use brand story arcs (BSA) to create micro-narratives. "
            "Paint the aspirational picture. Focus on emotional "
            "connection and brand world-building. Do NOT sell directly."
        ),
        "structure": (
            "Hook -> Aspirational vision -> Brand connection -> Soft CTA"
        ),
    },
    "mofu": {
        "approach": "feature-benefit, social proof, educational",
        "content_type": (
            "Feature-benefit pairs with social proof signals. "
            "Address specific pain points. Include credibility "
            "markers (numbers, credentials, testimonials). "
            "Position as the solution."
        ),
        "structure": (
            "Pain point -> Solution -> Proof point -> Value CTA"
        ),
    },
    "bofu": {
        "approach": "ROI-focused, testimonial-driven, offer-centric",
        "content_type": (
            "Direct ROI statements, customer testimonials, specific "
            "offers with terms. Include risk reversal (guarantees, "
            "trials). Create urgency without false scarcity."
        ),
        "structure": (
            "Proof/Offer -> Specifics -> Risk reversal -> Urgent CTA"
        ),
    },
    "retention": {
        "approach": "exclusive, appreciative, upsell-focused",
        "content_type": (
            "Acknowledge the customer relationship. Offer exclusive "
            "value or early access. Highlight new features or "
            "complementary products. Celebrate milestones."
        ),
        "structure": (
            "Recognition -> Exclusive value -> Next step -> Loyalty CTA"
        ),
    },
}


class PrimaryCopyGenerator:
    """Builds prompt section for primary ad copy generation."""

    def build_prompt_section(
        self, creative_context: dict[str, Any]
    ) -> str:
        """Build a prompt section for Claude call 2.

        Instructs Claude to generate 2-3 primary copy variants per
        audience x funnel in short, medium, and long lengths.

        Args:
            creative_context: Unified CampaignCreativeContext dict.

        Returns:
            Formatted prompt section string.
        """
        briefs = creative_context.get("creative_briefs", [])
        voice = creative_context.get("brand_voice", {})
        voice_matrix = voice.get("voice_matrix", {})
        positioning = creative_context.get("positioning", {})
        name_tagline = creative_context.get("name_tagline", {})
        story_arcs = creative_context.get("story_arcs", {})

        brand_name = name_tagline.get("brand_name", "")
        tagline = name_tagline.get("tagline", "")

        section = "## Primary Copy Generation Task\n\n"
        section += (
            "Generate primary ad copy for Meta Ads. Each ad set needs "
            "**2-3 copy variants**, each in **3 length tiers**.\n\n"
        )

        # Copy length tiers
        section += "### Copy Length Tiers\n"
        for length_key, spec in _COPY_LENGTHS.items():
            section += (
                f"- **{spec['label']}**: Max {spec['max_chars']} chars. "
                f"Use case: {spec['use_case']}\n"
            )
        section += "\n"

        # Brand voice
        if voice_matrix:
            section += "### Brand Voice (from BPV)\n"
            section += (
                f"{json.dumps(voice_matrix, default=str)[:500]}\n\n"
                "Maintain this voice consistently across all copy. "
                "Adapt intensity by funnel stage.\n\n"
            )

        # Brand name + tagline integration
        if brand_name or tagline:
            section += "### Brand Identity Integration\n"
            section += (
                f"Brand name: **{brand_name}**\n"
                f"Tagline: **{tagline}**\n"
                "Incorporate naturally — do not force. The brand name "
                "should appear at least once in medium/long copy. "
                "The tagline can be woven in or used as a sign-off.\n\n"
            )

        # Positioning context
        uvp = positioning.get("uvp", "")
        differentiators = positioning.get("differentiators", [])
        if uvp:
            section += f"### Value Proposition\n{uvp}\n"
            if differentiators:
                section += (
                    f"Key differentiators: "
                    f"{', '.join(str(d) for d in differentiators[:5])}\n"
                )
            section += "\n"

        # Story arcs for TOFU narrative use
        pitches = story_arcs.get("pitches", {})
        if pitches:
            section += "### Brand Story Elements (for TOFU)\n"
            pitch_15 = pitches.get("pitch_15s", {})
            if isinstance(pitch_15, dict):
                content = pitch_15.get("content", "")
            else:
                content = str(pitch_15)
            if content:
                section += f"15s pitch: {content}\n"
            section += (
                "Use these story elements as seeds for TOFU "
                "aspirational copy.\n\n"
            )

        # Per-brief copy instructions
        if not briefs:
            section += (
                "No creative briefs provided. Generate copy for "
                "a generic TOFU/MOFU/BOFU funnel.\n"
            )
            return section

        section += (
            f"### Copy Required ({len(briefs)} ad sets)\n\n"
        )

        for i, brief in enumerate(briefs, 1):
            ad_set_name = brief.get("ad_set_name", f"Ad Set {i}")
            persona = brief.get("persona", "General audience")
            funnel = brief.get("funnel_stage", "tofu").lower()
            theme = brief.get("messaging_theme", "")

            strategy = _FUNNEL_COPY_STRATEGIES.get(
                funnel, _FUNNEL_COPY_STRATEGIES["tofu"]
            )

            section += f"#### {i}. {ad_set_name}\n"
            section += f"- **Persona**: {persona}\n"
            section += f"- **Funnel**: {funnel.upper()}\n"
            section += f"- **Approach**: {strategy['approach']}\n"
            section += f"- **Content guidance**: {strategy['content_type']}\n"
            section += f"- **Structure**: {strategy['structure']}\n"
            if theme:
                section += f"- **Messaging theme**: {theme}\n"
            section += "\n"

        # Output format
        section += "### Primary Copy Output Format\n\n"
        section += (
            "Output a `primary_copy` array. Each entry:\n"
            "```json\n"
            "{\n"
            '  "ad_set_name": "string",\n'
            '  "variants": [\n'
            "    {\n"
            '      "variant_id": "copy_v1",\n'
            '      "short": {"text": "...", "char_count": int},\n'
            '      "medium": {"text": "...", "char_count": int},\n'
            '      "long": {"text": "...", "char_count": int},\n'
            '      "emotional_appeal": "string",\n'
            '      "key_message": "string"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n"
        )

        return section
