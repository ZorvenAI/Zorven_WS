"""Field type metadata for extraction prompt construction (J-03).

Maps each Company field to its expected type/shape so the LLM prompt
can describe what to extract rather than leaving it to infer from the
field name alone. Also contains the KEY/SECONDARY classification for
OG-03, and a local copy of the wizard page structure from Django's
``apps.onboarding.field_map`` — duplicated because the OIA service
cannot import from Django.
"""

from __future__ import annotations

from typing import Final

FIELD_TYPE_HINTS: Final[dict[str, str]] = {
    # Page 1 — Company Info
    "name": "string — Company or brand name",
    "legal_name": "string — Registered legal entity name",
    "description": "string — Brief company description",
    "industry": "string — Industry sector",
    "core_problem": "string — Main problem the company solves",
    "website": "string — URL",
    "address": "string — Street address",
    "city": "string — City",
    "state_province": "string — State or province",
    "postal_code": "string — Postal/ZIP code",
    "country": "string — Country",
    "founder_story": "string — Origin story in the founder's words",
    "trademark_status": "string — registered, pending, or none",
    "decision_maker": "string — Who signs off on brand/campaign decisions",
    # Page 2 — Brand Voice
    "brand_voice": (
        "string — one of: professional, friendly, bold, authoritative, "
        "playful, innovative, warm, technical"
    ),
    "vision_statement": "string — Vision statement",
    "mission_statement": "string — Mission statement",
    "values": "string — Comma-separated list of core values",
    "positioning_statement": "string — Market positioning statement",
    "tagline": "string — Brand tagline or slogan",
    "value_proposition": "string — Key value proposition",
    "elevator_pitch": "string — 30-second elevator pitch",
    "business_goals": "string — What the business wants to achieve",
    "color_palette_desc": "string — Color palette recommendations",
    "font_recommendations": "string — Typography recommendations",
    "messaging_guide": "string — Brand messaging guidelines",
    # Page 3 — Target Audience
    "target_audience": "string — Description of target customers",
    "demographics": "string — Demographic characteristics",
    "psychographics": "string — Psychological characteristics, values, interests",
    "pain_points": "string — Customer pain points and challenges",
    "desired_outcomes": "string — What customers want to achieve",
    "audience_languages": ('JSON array of BCP-47 tags, e.g. ["en-IN", "kn-IN"]'),
    "customer_proof": (
        "JSON array of objects: "
        '[{"type": "testimonial|review|case_study|award", '
        '"text": "...", "source": "...", "date": "..."}]'
    ),
    # Page 4 — Assets & Market
    "brand_asset_status": "string — What brand assets exist (logo, guidelines, none)",
    "competitors": (
        "JSON array of objects: " '[{"name": "...", "url": "...", "notes": "..."}]'
    ),
    "products_services": (
        "JSON array of objects: "
        '[{"name": "...", "description": "...", "price_range": "..."}]'
    ),
    "sales_channels": (
        "JSON array of objects: "
        '[{"channel": "online_store|marketplace|retail|wholesale|'
        'direct|social", "notes": "..."}]'
    ),
    "digital_presence": (
        "JSON object: "
        '{"website": "...", "instagram": "...", "facebook": "...", '
        '"linkedin": "...", "x": "...", "youtube": "...", '
        '"tiktok": "...", "google_business": "..."}'
    ),
    "marketing_budget_range": (
        "JSON object: "
        '{"currency": "INR", "min": 50000, "max": 200000, '
        '"period": "monthly"}'
    ),
}

WIZARD_PAGES: Final[dict[int, tuple[str, frozenset[str]]]] = {
    1: (
        "Company Info",
        frozenset(
            {
                "name",
                "legal_name",
                "description",
                "industry",
                "core_problem",
                "website",
                "address",
                "city",
                "state_province",
                "postal_code",
                "country",
                "founder_story",
                "trademark_status",
                "decision_maker",
            }
        ),
    ),
    2: (
        "Brand Voice",
        frozenset(
            {
                "brand_voice",
                "vision_statement",
                "mission_statement",
                "values",
                "positioning_statement",
                "tagline",
                "value_proposition",
                "elevator_pitch",
                "business_goals",
                "color_palette_desc",
                "font_recommendations",
                "messaging_guide",
            }
        ),
    ),
    3: (
        "Target Audience",
        frozenset(
            {
                "target_audience",
                "demographics",
                "psychographics",
                "pain_points",
                "desired_outcomes",
                "audience_languages",
                "customer_proof",
            }
        ),
    ),
    4: (
        "Assets & Market",
        frozenset(
            {
                "brand_asset_status",
                "competitors",
                "products_services",
                "sales_channels",
                "digital_presence",
                "marketing_budget_range",
            }
        ),
    ),
}


def all_mapped_fields() -> frozenset[str]:
    """All fields across all wizard pages."""
    return frozenset(f for _label, fields in WIZARD_PAGES.values() for f in fields)


KEY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "name",
        "description",
        "industry",
        "core_problem",
        "website",
        "target_audience",
        "brand_voice",
        "vision_statement",
        "mission_statement",
        "values",
        "positioning_statement",
        "tagline",
        "value_proposition",
        "demographics",
        "psychographics",
        "pain_points",
        "desired_outcomes",
    }
)
