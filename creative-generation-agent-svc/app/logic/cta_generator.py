"""SKL-CGA-09: CTA Generator.

Builds a prompt section for Claude call 2 that instructs Claude to
generate 2-3 CTA variants per audience x funnel using Meta CTA button
enums, scored on urgency and clarity.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Meta Ads CTA button enum values
META_CTA_BUTTONS: list[str] = [
    "LEARN_MORE",
    "SHOP_NOW",
    "SIGN_UP",
    "DOWNLOAD",
    "GET_OFFER",
    "BOOK_NOW",
    "CONTACT_US",
    "WATCH_MORE",
    "APPLY_NOW",
    "SUBSCRIBE",
    "GET_QUOTE",
    "ORDER_NOW",
    "SEND_MESSAGE",
    "LISTEN_NOW",
    "SEE_MENU",
    "INSTALL_NOW",
    "USE_APP",
    "PLAY_GAME",
    "GET_DIRECTIONS",
    "CALL_NOW",
]

# Funnel stage -> recommended CTA buttons
_FUNNEL_CTA_MAPPING: dict[str, dict[str, Any]] = {
    "tofu": {
        "recommended": ["LEARN_MORE", "WATCH_MORE"],
        "also_valid": ["SUBSCRIBE", "LISTEN_NOW"],
        "rationale": (
            "TOFU CTAs should invite exploration without commitment. "
            "Low friction, curiosity-driven actions."
        ),
    },
    "mofu": {
        "recommended": ["GET_OFFER", "WATCH_MORE", "GET_QUOTE"],
        "also_valid": ["LEARN_MORE", "DOWNLOAD", "SEND_MESSAGE"],
        "rationale": (
            "MOFU CTAs should offer value exchange — content, quotes, "
            "demos — building toward commitment."
        ),
    },
    "bofu": {
        "recommended": ["SHOP_NOW", "SIGN_UP", "BOOK_NOW"],
        "also_valid": [
            "ORDER_NOW",
            "APPLY_NOW",
            "GET_OFFER",
            "CONTACT_US",
        ],
        "rationale": (
            "BOFU CTAs drive direct conversion. Use action-oriented, "
            "decisive language with urgency."
        ),
    },
    "retention": {
        "recommended": ["SHOP_NOW", "GET_OFFER", "BOOK_NOW"],
        "also_valid": ["LEARN_MORE", "SUBSCRIBE", "SEND_MESSAGE"],
        "rationale": (
            "Retention CTAs encourage repeat action or upsell. "
            "Leverage existing relationship and trust."
        ),
    },
}


class CTAGenerator:
    """Builds prompt section for CTA generation."""

    def build_prompt_section(self, creative_context: dict[str, Any]) -> str:
        """Build a prompt section for Claude call 2.

        Instructs Claude to generate 2-3 CTA variants per
        audience x funnel using Meta CTA button enums.

        Args:
            creative_context: Unified CampaignCreativeContext dict.

        Returns:
            Formatted prompt section string.
        """
        briefs = creative_context.get("creative_briefs", [])
        positioning = creative_context.get("positioning", {})

        section = "## CTA Generation Task\n\n"
        section += (
            "Generate call-to-action variants for Meta Ads. Each ad "
            "set needs **2-3 CTA variants**, each using a valid Meta "
            "CTA button enum value.\n\n"
        )

        # Available CTA buttons
        section += "### Available Meta CTA Buttons\n"
        section += "You MUST use one of these exact enum values for " "`cta_button`:\n"
        for cta in META_CTA_BUTTONS:
            section += f"- `{cta}`\n"
        section += "\n"

        # Positioning for CTA messaging
        uvp = positioning.get("uvp", "")
        if uvp:
            section += (
                f"### Value Proposition Context\n{uvp}\n"
                "CTAs should reinforce this value proposition.\n\n"
            )

        # Per-brief CTA instructions
        if not briefs:
            section += (
                "No creative briefs provided. Generate CTAs for "
                "a generic TOFU/MOFU/BOFU funnel.\n"
            )
            return section

        section += f"### CTAs Required ({len(briefs)} ad sets)\n\n"

        for i, brief in enumerate(briefs, 1):
            ad_set_name = brief.get("ad_set_name", f"Ad Set {i}")
            persona = brief.get("persona", "General audience")
            funnel = brief.get("funnel_stage", "tofu").lower()

            mapping = _FUNNEL_CTA_MAPPING.get(funnel, _FUNNEL_CTA_MAPPING["tofu"])

            section += f"#### {i}. {ad_set_name}\n"
            section += f"- **Persona**: {persona}\n"
            section += f"- **Funnel**: {funnel.upper()}\n"
            section += f"- **Rationale**: {mapping['rationale']}\n"
            section += (
                f"- **Recommended buttons**: " f"{', '.join(mapping['recommended'])}\n"
            )
            section += f"- **Also valid**: " f"{', '.join(mapping['also_valid'])}\n"
            section += "\n"

        # Output format
        section += "### CTA Output Format\n\n"
        section += (
            "Output a `ctas` array. Each entry:\n"
            "```json\n"
            "{\n"
            '  "ad_set_name": "string",\n'
            '  "cta_variants": [\n'
            "    {\n"
            '      "cta_button": "META_ENUM_VALUE",\n'
            '      "cta_text": "Custom button label (max 30 chars)",\n'
            '      "urgency_score": 0-100,\n'
            '      "clarity_score": 0-100,\n'
            '      "rationale": "why this CTA works for this audience x funnel"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n\n"
            "**Scoring guidelines**:\n"
            "- `urgency_score`: How much time pressure the CTA creates "
            "(0 = no urgency, 100 = immediate action required)\n"
            "- `clarity_score`: How clear the expected action is "
            "(0 = vague, 100 = perfectly clear next step)\n"
        )

        return section
