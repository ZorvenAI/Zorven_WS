"""SKL-CGA-07: Hook Generator.

Builds a prompt section for Claude call 2 that instructs Claude to
generate 3-5 hook variants per audience x funnel combination,
scored on scroll-stop power, with funnel-specific hook strategies.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Funnel stage -> hook strategy mapping
_FUNNEL_HOOK_STRATEGIES: dict[str, dict[str, Any]] = {
    "tofu": {
        "patterns": [
            "curiosity gap (open loop that demands resolution)",
            "emotional trigger (tap into aspiration or fear of missing out)",
            "trend reference (leverage current cultural moment)",
            "bold claim (surprising statistic or counterintuitive statement)",
            "question hook (rhetorical question targeting audience pain)",
        ],
        "tone": "attention-grabbing, scroll-stopping, emotionally evocative",
        "goal": "Stop the scroll and spark immediate curiosity",
    },
    "mofu": {
        "patterns": [
            'pain-point agitation ("Tired of...?" / "Still struggling with...?")',
            '"Did you know" revelation (educational fact that reframes the problem)',
            "social proof hook (reference success stories or numbers)",
            "comparison hook (before/after, with/without framing)",
            "myth-busting hook (challenge common misconception)",
        ],
        "tone": "educational, empathetic, insight-driven",
        "goal": "Build consideration by demonstrating understanding",
    },
    "bofu": {
        "patterns": [
            "urgency trigger (time-limited, quantity-limited)",
            "proof hook (specific results, testimonial quote)",
            "scarcity signal (limited availability, exclusive access)",
            "risk reversal (guarantee, free trial, money-back)",
            "direct offer (clear value proposition with CTA)",
        ],
        "tone": "confident, urgent, action-oriented",
        "goal": "Drive immediate conversion action",
    },
    "retention": {
        "patterns": [
            "insider exclusive (VIP access, early bird)",
            "loyalty reward (appreciation, special offer)",
            "community belonging (you're part of something)",
            "upsell value (unlock the next level)",
            "milestone celebration (congratulations on your journey)",
        ],
        "tone": "appreciative, exclusive, personal",
        "goal": "Re-engage and deepen brand loyalty",
    },
}


class HookGenerator:
    """Builds prompt section for ad hook generation."""

    def build_prompt_section(self, creative_context: dict[str, Any]) -> str:
        """Build a prompt section for Claude call 2.

        Instructs Claude to generate 3-5 hook variants per
        audience x funnel, each scored on scroll_stop_power 0-100.

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

        section = "## Hook Generation Task\n\n"
        section += (
            "Generate scroll-stopping hooks for Meta Ads. Each hook "
            "must be **125 characters or fewer** and designed to stop "
            "the thumb-scroll in under 1.5 seconds.\n\n"
        )

        # Brand voice context
        if voice_matrix:
            section += "### Brand Voice\n"
            section += f"Voice matrix: {json.dumps(voice_matrix, default=str)[:500]}\n"
            section += (
                "All hooks must align with this voice. Adapt tone "
                "by funnel stage while maintaining brand consistency.\n\n"
            )

        # Positioning for hook messaging
        uvp = positioning.get("uvp", "")
        if uvp:
            section += f"### Value Proposition\n{uvp}\n\n"

        brand_name = name_tagline.get("brand_name", "")
        tagline = name_tagline.get("tagline", "")
        if brand_name or tagline:
            section += "### Brand Identity\n"
            if brand_name:
                section += f"- **Name**: {brand_name}\n"
            if tagline:
                section += f"- **Tagline**: {tagline}\n"
            section += "\n"

        # Per-brief hook instructions
        if not briefs:
            section += (
                "No creative briefs provided. Generate hooks for "
                "a generic TOFU/MOFU/BOFU funnel.\n"
            )
            return section

        section += (
            f"### Hooks Required ({len(briefs)} ad sets)\n\n"
            "Generate **3-5 hooks per ad set** using the strategies "
            "specified for each funnel stage.\n\n"
        )

        for i, brief in enumerate(briefs, 1):
            ad_set_name = brief.get("ad_set_name", f"Ad Set {i}")
            persona = brief.get("persona", "General audience")
            funnel = brief.get("funnel_stage", "tofu").lower()
            theme = brief.get("messaging_theme", "")

            strategy = _FUNNEL_HOOK_STRATEGIES.get(
                funnel, _FUNNEL_HOOK_STRATEGIES["tofu"]
            )

            section += f"#### {i}. {ad_set_name}\n"
            section += f"- **Persona**: {persona}\n"
            section += f"- **Funnel**: {funnel.upper()}\n"
            section += f"- **Goal**: {strategy['goal']}\n"
            section += f"- **Tone**: {strategy['tone']}\n"
            if theme:
                section += f"- **Messaging theme**: {theme}\n"
            section += "- **Hook patterns to use**:\n"
            for pattern in strategy["patterns"]:
                section += f"  - {pattern}\n"
            section += "\n"

        # Output format
        section += "### Hook Output Format\n\n"
        section += (
            "Output a `hooks` array. Each entry:\n"
            "```json\n"
            "{\n"
            '  "ad_set_name": "string",\n'
            '  "hooks": [\n'
            "    {\n"
            '      "hook_text": "string (max 125 chars)",\n'
            '      "hook_pattern": "curiosity|emotional|trend|pain_point|urgency|...",\n'
            '      "scroll_stop_power": 0-100,\n'
            '      "char_count": int,\n'
            '      "rationale": "why this hook works for this audience"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n"
        )

        return section
