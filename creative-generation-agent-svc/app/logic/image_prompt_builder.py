"""SKL-CGA-04: Image Prompt Builder.

Builds a prompt section for Claude call 1 that instructs Claude to
generate detailed AI image generation prompts for each audience x funnel
combination, with specifications for subject, composition, mood,
color palette, and negative prompts.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Aspect ratio composition guidance
_COMPOSITION_GUIDANCE: dict[str, str] = {
    "1:1": (
        "centered composition, balanced layout, works for feed posts; "
        "subject fills 60-70% of frame"
    ),
    "9:16": (
        "vertical composition, strong top-third focus for text overlay; "
        "subject in lower 2/3, breathing room at top for headline"
    ),
    "16:9": (
        "horizontal/landscape composition, cinematic feel; "
        "subject positioned using rule of thirds, wide environmental context"
    ),
}

# Funnel stage -> image subject guidance
_FUNNEL_SUBJECT_GUIDANCE: dict[str, str] = {
    "tofu": (
        "lifestyle-oriented, aspirational, emotionally evocative; "
        "show the desired end state, not the product directly"
    ),
    "mofu": (
        "product-in-context, feature highlighting, social proof elements; "
        "show the product solving a real problem"
    ),
    "bofu": (
        "clear product shots, offer visualization, trust indicators; "
        "direct product imagery with pricing/offer overlays"
    ),
    "retention": (
        "community, loyalty, behind-the-scenes, exclusive access; "
        "show belonging and insider status"
    ),
}


class ImagePromptBuilder:
    """Builds prompt section for AI image generation instructions."""

    def build_prompt_section(
        self, creative_context: dict[str, Any]
    ) -> str:
        """Build a prompt section for Claude call 1.

        Instructs Claude to generate detailed AI image prompts for each
        audience x funnel combination with 3 distinct variants per brief.

        Args:
            creative_context: Unified CampaignCreativeContext dict.

        Returns:
            Formatted prompt section string.
        """
        briefs = creative_context.get("creative_briefs", [])
        visual = creative_context.get("brand_visual", {})
        company = creative_context.get("company", {})
        positioning = creative_context.get("positioning", {})
        name_tagline = creative_context.get("name_tagline", {})

        archetype = visual.get("archetype", "")
        color_palette = visual.get(
            "color_palette_desc",
            company.get("color_palette_desc", ""),
        )
        industry = visual.get(
            "industry", company.get("industry", "")
        )
        brand_name = name_tagline.get("brand_name", "") or company.get("name", "")
        tagline = name_tagline.get("tagline", "")
        description = company.get("description", "")
        products = company.get("products", [])
        uvp = positioning.get("uvp", "")

        section = "## AI Image Prompt Generation Task\n\n"
        section += (
            "Generate detailed AI image generation prompts for each "
            "audience x funnel combination. These prompts will be fed "
            "to an AI image generator.\n\n"
        )

        # Brand identity — CRITICAL for relevant image generation
        section += "### Brand Identity\n"
        if brand_name:
            section += f"- **Brand name**: {brand_name}\n"
        if tagline:
            section += f"- **Tagline**: {tagline}\n"
        if description:
            section += f"- **Description**: {description}\n"
        if industry:
            section += f"- **Industry**: {industry}\n"
        if products:
            product_list = ", ".join(str(p) for p in products[:10])
            section += f"- **Products/Services**: {product_list}\n"
        if uvp:
            section += f"- **Value proposition**: {uvp}\n"
        section += "\n"

        section += (
            "**IMPORTANT**: All generated image prompts MUST be directly "
            "relevant to the brand above. Images should clearly represent "
            "the brand's products, services, or the lifestyle associated "
            "with the brand. Do NOT generate generic stock-photo-style "
            "images. Every image should be usable as a brand asset.\n\n"
        )

        # Brand visual style
        section += "### Brand Visual Style\n"
        if archetype:
            section += f"- **Archetype**: {archetype}\n"
        if color_palette:
            section += f"- **Color palette**: {color_palette}\n"
        logo_url = visual.get("logo_url", "")
        if logo_url:
            section += f"- **Logo reference**: {logo_url}\n"
        section += "\n"

        # Composition guidance per aspect ratio
        section += "### Aspect Ratio Compositions\n"
        section += (
            "Each prompt must be generated for 3 aspect ratios:\n"
        )
        for ratio, guidance in _COMPOSITION_GUIDANCE.items():
            section += f"- **{ratio}**: {guidance}\n"
        section += "\n"

        # Per-brief instructions
        if not briefs:
            section += (
                "No creative briefs provided. Generate image prompts "
                "for a generic 3-stage funnel.\n"
            )
            return section

        section += (
            f"### Image Prompts Required ({len(briefs)} ad sets)\n\n"
            "For each ad set, generate **3 distinct prompt variants** "
            "that offer visual diversity while maintaining brand "
            "consistency.\n\n"
        )

        personas = creative_context.get("audience_personas", [])
        persona_map: dict[str, dict[str, Any]] = {}
        for p in personas:
            if isinstance(p, dict):
                name = p.get("name", "")
                if name:
                    persona_map[name.lower()] = p

        for i, brief in enumerate(briefs, 1):
            ad_set_name = brief.get("ad_set_name", f"Ad Set {i}")
            persona = brief.get("persona", "General audience")
            funnel = brief.get("funnel_stage", "tofu").lower()
            theme = brief.get("messaging_theme", "")
            variant_count = brief.get("variant_count", 3)

            funnel_guidance = _FUNNEL_SUBJECT_GUIDANCE.get(
                funnel, _FUNNEL_SUBJECT_GUIDANCE["tofu"]
            )

            # Enrich with persona lifestyle data
            persona_data = persona_map.get(
                persona.lower() if isinstance(persona, str) else "", {}
            )
            lifestyle = persona_data.get("lifestyle", "")
            interests = persona_data.get("interests", [])

            section += f"#### {i}. {ad_set_name}\n"
            section += f"- **Persona**: {persona}\n"
            section += f"- **Funnel stage**: {funnel.upper()}\n"
            if theme:
                section += f"- **Messaging theme**: {theme}\n"
            section += f"- **Subject matter**: {funnel_guidance}\n"
            if lifestyle:
                section += f"- **Persona lifestyle**: {lifestyle}\n"
            if interests:
                section += (
                    f"- **Persona interests**: "
                    f"{', '.join(str(x) for x in interests[:5])}\n"
                )
            section += f"- **Variants needed**: {variant_count}\n"
            section += "\n"

        # Output format specification
        section += "### Image Prompt Output Format\n\n"
        section += (
            "Output an `image_prompts` array. Each entry:\n"
            "```json\n"
            "{\n"
            '  "ad_set_name": "string",\n'
            '  "variant_id": "v1|v2|v3",\n'
            '  "prompt_text": "detailed generation prompt (50-150 words)",\n'
            '  "negative_prompt": "what to avoid in the image",\n'
            '  "style": "photorealistic|illustration|3d_render|flat_design",\n'
            '  "mood": "string describing emotional quality",\n'
            '  "color_guidance": "specific color instructions",\n'
            '  "subject": "primary subject description",\n'
            '  "diversity_note": "how this variant differs from others"\n'
            "}\n"
            "```\n\n"
            "Ensure each variant set has meaningful visual diversity:\n"
            "- Variant 1: hero/primary concept\n"
            "- Variant 2: alternative angle/perspective\n"
            "- Variant 3: bold/experimental variation\n"
        )

        return section
