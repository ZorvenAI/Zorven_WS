"""SKL-CAA-07: Audience Targeting Builder.

Builds prompt section for Claude call 1: APA personas -> Meta targeting
specs (demographics, interests, behaviors, custom/lookalike audiences).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AudienceTargetingBuilder:
    """Build audience targeting prompt section for Claude call 1."""

    def build_prompt_section(
        self,
        strategy_context: dict[str, Any],
        customer_data: dict[str, Any] | None = None,
    ) -> str:
        """Build audience targeting prompt section."""
        section = "## Audience Targeting Task\n\n"

        # APA personas
        personas = strategy_context.get("audience_personas", {})
        if personas:
            persona_list = personas.get("personas", [])
            if persona_list:
                section += f"### Audience Personas ({len(persona_list)} identified)\n"
                for i, p in enumerate(persona_list[:5], 1):
                    name = (
                        p.get("name", f"Persona {i}") if isinstance(p, dict) else str(p)
                    )
                    section += f"{i}. **{name}**"
                    if isinstance(p, dict):
                        age = p.get("age_range", "")
                        if age:
                            section += f" (Age: {age})"
                        interests = p.get("interests", [])
                        if interests:
                            section += f" — Interests: {', '.join(interests[:5])}"
                    section += "\n"
            section += "\n"

        # VoC insights for behavioral targeting
        voc = strategy_context.get("voc_insights", {})
        if voc:
            section += "### Voice of Customer Insights\n"
            pain_points = voc.get("pain_points", [])
            if pain_points:
                section += (
                    f"Key pain points: {', '.join(str(p) for p in pain_points[:5])}\n"
                )
            section += "\n"

        # Customer data from Odoo
        if customer_data and customer_data.get("available"):
            section += "### CRM Custom Audiences\n"
            for aud in customer_data.get("custom_audiences", []):
                section += (
                    f"- {aud['name']} ({aud['size']} users) "
                    f"→ use as custom audience + create lookalike\n"
                )
            section += "\n"

        section += (
            "For each funnel stage, output `targeting_specs` array with:\n"
            "- ad_set_name, funnel_stage\n"
            "- demographics: {age_min, age_max, genders, locations}\n"
            "- interests: [Meta interest targeting keywords]\n"
            "- behaviors: [Meta behavioral targeting]\n"
            "- custom_audiences: [if CRM data available]\n"
            "- lookalike_audiences: [if CRM data available]\n"
            "- exclusions: [audiences to exclude]\n"
            "- estimated_audience_size: approximate reach\n"
        )

        return section
