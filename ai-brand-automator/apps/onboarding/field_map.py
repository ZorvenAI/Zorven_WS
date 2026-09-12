"""Which wizard page each reviewable field belongs to.

The review page groups provenance by the page an operator already knows, so
they read the extraction in the same order they would have typed it. That
grouping needs a field-to-page map, and the B-06 card is specific about where
it lives: here, "as data shared with J-02's extraction target list, so
extraction and review cannot disagree about where a field belongs."

J-02 does not exist yet, so this file *sets* that contract rather than
consuming it. Anything that needs a per-page field list should import from
here rather than restating it.

Pure data with no Django imports, so it can be read, diffed and tested on its
own — and so a test can assert it covers every field without standing up an
app registry first.
"""

from __future__ import annotations

#: Fields that exist on Company but are never reviewed: bookkeeping the agent
#: does not extract and an operator has no opinion about.
NOT_REVIEWABLE = frozenset({"id", "tenant", "created_at", "updated_at"})

#: Returned for a field with no page. Deliberately a real group rather than a
#: silent drop — a field missing from the map should show up in review looking
#: wrong, not disappear from it.
UNMAPPED = "unmapped"

#: page number -> (label, fields). Ordered to match the wizard the operator
#: walked, which is the whole point of grouping this way.
WIZARD_PAGES: dict[int, tuple[str, frozenset[str]]] = {
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
                # Brand-identity outputs. The wizard has no identity page —
                # the onboarding PDF gives them their own section, but the
                # five steps do not — so they sit with the voice they express.
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
    # Page 5 is Review itself: it displays the others and owns no fields.
}

#: field -> page number, flattened once at import.
_FIELD_TO_PAGE: dict[str, int] = {
    field: page for page, (_label, fields) in WIZARD_PAGES.items() for field in fields
}


def page_for(field_name: str) -> int | None:
    """The wizard page *field_name* belongs to, or None if unmapped."""
    return _FIELD_TO_PAGE.get(field_name)


def label_for(page: int | None) -> str:
    """Human label for a page number, or the unmapped group."""
    if page is None:
        return UNMAPPED
    return WIZARD_PAGES[page][0]


def all_mapped_fields() -> frozenset[str]:
    return frozenset(_FIELD_TO_PAGE)
