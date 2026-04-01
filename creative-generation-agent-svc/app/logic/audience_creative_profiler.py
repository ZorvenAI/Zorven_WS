"""SKL-CGA-02: Audience Creative Profiler.

Builds a prompt section for Claude call 1 that maps each
audience x funnel combination to visual style, emotional tone,
color emphasis, and copy approach based on brand archetype.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Archetype -> visual mood mapping for image generation guidance
ARCHETYPE_VISUAL_MOODS: dict[str, dict[str, str]] = {
    "Hero": {
        "visual_style": "bold and dynamic",
        "image_subjects": "empowered individuals, action moments, achievements",
        "emotional_tone": "confident, triumphant, powerful",
        "color_emphasis": "strong contrast, deep blues, vibrant reds, metallic golds",
        "copy_approach": "challenge-driven, empowering calls to action",
    },
    "Caregiver": {
        "visual_style": "warm and soft",
        "image_subjects": "nurturing moments, community, togetherness, safety",
        "emotional_tone": "compassionate, trustworthy, gentle",
        "color_emphasis": "soft pastels, warm whites, gentle greens, calming blues",
        "copy_approach": "empathetic, supportive, reassuring language",
    },
    "Sage": {
        "visual_style": "clean and intellectual",
        "image_subjects": "knowledge symbols, clarity, structured environments",
        "emotional_tone": "wise, authoritative, enlightening",
        "color_emphasis": "navy, white, silver, muted earth tones",
        "copy_approach": "data-driven, thought-provoking, educational",
    },
    "Creator": {
        "visual_style": "vibrant and artistic",
        "image_subjects": "creative process, unique designs, artistic expression",
        "emotional_tone": "imaginative, innovative, expressive",
        "color_emphasis": "rich saturated colors, unexpected combinations, artistic palettes",
        "copy_approach": "inspirational, visionary, celebrate uniqueness",
    },
    "Explorer": {
        "visual_style": "adventurous and natural",
        "image_subjects": "open landscapes, journeys, discovery, freedom",
        "emotional_tone": "free-spirited, curious, adventurous",
        "color_emphasis": "earthy tones, sky blues, sunset oranges, forest greens",
        "copy_approach": "discovery-oriented, freedom-focused, experiential",
    },
    "Ruler": {
        "visual_style": "luxurious and authoritative",
        "image_subjects": "premium settings, exclusivity, leadership, refinement",
        "emotional_tone": "prestigious, commanding, sophisticated",
        "color_emphasis": "black, gold, deep purple, rich burgundy",
        "copy_approach": "exclusive, status-driven, premium positioning",
    },
    "Magician": {
        "visual_style": "transformative and ethereal",
        "image_subjects": "transformation moments, before/after, wonder, possibility",
        "emotional_tone": "awe-inspiring, visionary, mystical",
        "color_emphasis": "deep purples, iridescent tones, starlight silver, cosmic blues",
        "copy_approach": "transformational, possibility-focused, visionary",
    },
    "Outlaw": {
        "visual_style": "edgy and disruptive",
        "image_subjects": "rule-breaking, counter-culture, bold statements",
        "emotional_tone": "rebellious, provocative, unapologetic",
        "color_emphasis": "black, red, raw textures, high contrast",
        "copy_approach": "provocative, challenge the norm, authentic rebellion",
    },
    "Jester": {
        "visual_style": "playful and colorful",
        "image_subjects": "joy, humor, lighthearted moments, surprise",
        "emotional_tone": "fun, witty, energetic",
        "color_emphasis": "bright primaries, pops of neon, cheerful yellows",
        "copy_approach": "humorous, witty, playful wordplay",
    },
    "Lover": {
        "visual_style": "sensual and intimate",
        "image_subjects": "connection, beauty, desire, intimacy",
        "emotional_tone": "passionate, alluring, romantic",
        "color_emphasis": "rich reds, rose golds, soft pinks, warm tones",
        "copy_approach": "emotional connection, desire-driven, sensory language",
    },
    "Everyman": {
        "visual_style": "relatable and authentic",
        "image_subjects": "everyday life, real people, genuine moments",
        "emotional_tone": "friendly, approachable, honest",
        "color_emphasis": "natural tones, comfortable neutrals, familiar hues",
        "copy_approach": "conversational, relatable, inclusive language",
    },
    "Innocent": {
        "visual_style": "pure and optimistic",
        "image_subjects": "simplicity, nature, happiness, wholesome moments",
        "emotional_tone": "hopeful, sincere, optimistic",
        "color_emphasis": "whites, light blues, soft yellows, fresh greens",
        "copy_approach": "simple, honest, uplifting, positive messaging",
    },
}

# Default mood for unknown archetypes
_DEFAULT_MOOD: dict[str, str] = {
    "visual_style": "modern and professional",
    "image_subjects": "professional settings, product lifestyle shots",
    "emotional_tone": "confident, trustworthy",
    "color_emphasis": "brand colors, clean backgrounds",
    "copy_approach": "clear, benefit-focused, professional",
}

# Funnel-specific creative direction
_FUNNEL_CREATIVE: dict[str, dict[str, str]] = {
    "tofu": {
        "goal": "Stop the scroll and spark curiosity",
        "image_focus": "emotionally evocative, lifestyle-oriented, story-driven",
        "copy_focus": "curiosity hooks, emotional triggers, trend references",
    },
    "mofu": {
        "goal": "Educate and build consideration",
        "image_focus": "product in context, feature highlights, social proof",
        "copy_focus": "pain-point solutions, feature-benefit pairs, credibility signals",
    },
    "bofu": {
        "goal": "Drive conversion and urgency",
        "image_focus": "clear product shots, offer visuals, trust badges",
        "copy_focus": "urgency, scarcity, ROI proof, testimonials, strong CTAs",
    },
    "retention": {
        "goal": "Re-engage and deepen loyalty",
        "image_focus": "community, loyalty rewards, behind-the-scenes",
        "copy_focus": "exclusivity, appreciation, upsell value",
    },
}


class AudienceCreativeProfiler:
    """Builds prompt section mapping audience x funnel to creative direction."""

    def build_prompt_section(
        self, creative_context: dict[str, Any]
    ) -> str:
        """Build a prompt section for Claude call 1.

        For each audience x funnel combination in creative_briefs,
        describes the visual style, image subjects, emotional tone,
        color emphasis, and copy approach.

        Args:
            creative_context: Unified CampaignCreativeContext dict.

        Returns:
            Formatted prompt section string.
        """
        briefs = creative_context.get("creative_briefs", [])
        visual = creative_context.get("brand_visual", {})
        company = creative_context.get("company", {})
        name_tagline = creative_context.get("name_tagline", {})
        archetype = visual.get("archetype", "")

        brand_name = name_tagline.get("brand_name", "") or company.get("name", "")
        description = company.get("description", "")
        industry = visual.get("industry", company.get("industry", ""))

        # Resolve archetype mood
        mood = ARCHETYPE_VISUAL_MOODS.get(archetype, _DEFAULT_MOOD)

        section = "## Audience Creative Profiling\n\n"
        if brand_name:
            section += f"Brand: **{brand_name}**"
            if industry:
                section += f" ({industry})"
            section += "\n"
        if description:
            section += f"About: {description[:300]}\n"
        section += (
            f"Brand archetype: **{archetype or 'Not specified'}**\n"
            f"Visual style: {mood['visual_style']}\n"
            f"Emotional tone: {mood['emotional_tone']}\n"
            f"Color emphasis: {mood['color_emphasis']}\n\n"
        )

        if not briefs:
            section += (
                "No creative briefs available. Generate creative profiles "
                "for a generic TOFU/MOFU/BOFU funnel approach.\n"
            )
            return section

        section += (
            f"Generate creative profiles for {len(briefs)} "
            f"audience x funnel combinations:\n\n"
        )

        for i, brief in enumerate(briefs, 1):
            ad_set_name = brief.get("ad_set_name", f"Ad Set {i}")
            persona = brief.get("persona", "General audience")
            funnel = brief.get("funnel_stage", "tofu").lower()
            theme = brief.get("messaging_theme", "")
            placements = brief.get("placements", [])

            funnel_dir = _FUNNEL_CREATIVE.get(
                funnel, _FUNNEL_CREATIVE["tofu"]
            )

            section += f"### {i}. {ad_set_name}\n"
            section += f"- **Persona**: {persona}\n"
            section += f"- **Funnel stage**: {funnel.upper()}\n"
            if theme:
                section += f"- **Messaging theme**: {theme}\n"
            if placements:
                section += (
                    f"- **Placements**: {', '.join(placements)}\n"
                )
            section += f"- **Creative goal**: {funnel_dir['goal']}\n"
            section += (
                f"- **Visual style**: {mood['visual_style']} — "
                f"{funnel_dir['image_focus']}\n"
            )
            section += (
                f"- **Image subjects**: {mood['image_subjects']}\n"
            )
            section += (
                f"- **Emotional tone**: {mood['emotional_tone']}\n"
            )
            section += (
                f"- **Color emphasis**: {mood['color_emphasis']}\n"
            )
            section += (
                f"- **Copy approach**: {mood['copy_approach']} — "
                f"{funnel_dir['copy_focus']}\n"
            )
            section += "\n"

        section += (
            "Output a `creative_profiles` array with one entry per "
            "audience x funnel, each containing: ad_set_name, persona, "
            "funnel_stage, visual_direction (style, subjects, mood, "
            "color_palette), copy_direction (approach, tone, hooks_style, "
            "cta_style), emotional_resonance_target.\n"
        )

        return section
