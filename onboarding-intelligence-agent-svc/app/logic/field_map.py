"""Shared field → workflow_target mapping (Design §10.1).

Both prepared questions (C-03) and ad-hoc questions (G-05) resolve
target_field through this map so the workflow_target is consistent
regardless of how the question was surfaced.
"""

from __future__ import annotations

import re
from typing import Final, Literal

WorkflowTarget = Literal["WF1", "WF2", "WF3"]

FIELD_MAP: Final[dict[str, WorkflowTarget]] = {
    # WF1 — company identity
    "name": "WF1",
    "company_name": "WF1",
    "legal_name": "WF1",
    "founded_year": "WF1",
    "founding_year": "WF1",
    "founder_story": "WF1",
    "founders": "WF1",
    "products_services": "WF1",
    "products": "WF1",
    "services": "WF1",
    "business_goals": "WF1",
    "goals": "WF1",
    "industry": "WF1",
    "website": "WF1",
    "mission": "WF1",
    "vision": "WF1",
    "values": "WF1",
    "history": "WF1",
    "location": "WF1",
    "headquarters": "WF1",
    "employees": "WF1",
    "team_size": "WF1",
    "revenue": "WF1",
    # WF2 — brand strategy
    "brand_asset_status": "WF2",
    "brand_assets": "WF2",
    "brand_guidelines": "WF2",
    "brand_colors": "WF2",
    "brand_fonts": "WF2",
    "trademark_status": "WF2",
    "trademarks": "WF2",
    "competitors": "WF2",
    "competition": "WF2",
    "digital_presence": "WF2",
    "social_media": "WF2",
    "audience_languages": "WF2",
    "languages": "WF2",
    "decision_maker": "WF2",
    "target_audience": "WF2",
    "brand_voice": "WF2",
    "brand_tone_of_voice": "WF2",
    "tone_of_voice": "WF2",
    "brand_personality": "WF2",
    "brand_positioning": "WF2",
    "differentiation": "WF2",
    "photos": "WF2",
    "videos": "WF2",
    "media_assets": "WF2",
    "visual_assets": "WF2",
    "signature_dishes": "WF2",
    # WF3 — go-to-market
    "marketing_budget_range": "WF3",
    "marketing_budget": "WF3",
    "budget": "WF3",
    "sales_channels": "WF3",
    "distribution": "WF3",
    "customer_proof": "WF3",
    "testimonials": "WF3",
    "case_studies": "WF3",
    "pricing": "WF3",
    "pricing_strategy": "WF3",
    "campaigns": "WF3",
    "campaign_objective": "WF3",
    "advertising": "WF3",
    "ad_creative": "WF3",
    "ad_hooks": "WF3",
    "primary_kpi": "WF3",
    "kpi": "WF3",
    "ideal_customer_profile": "WF3",
    "retail_locations": "WF3",
    "stores": "WF3",
    "partnerships": "WF3",
    "monthly_revenue": "WF3",
}

_NORMALISE_RE = re.compile(r"[\s\-]+")

DEFAULT_WORKFLOW_TARGET: Final[WorkflowTarget] = "WF1"

_TEXT_PATTERNS: Final[list[tuple[re.Pattern[str], WorkflowTarget]]] = [
    (
        re.compile(
            r"\b(ad campaign|ad creative|meta ad|facebook ad|instagram ad|google ad|advertising campaign|campaign objective|run.{0,15}ads)\b",
            re.I,
        ),
        "WF3",
    ),
    (
        re.compile(
            r"\b(marketing budget|ad spend|advertising budget|monthly budget.{0,15}(market|ad|campaign))\b",
            re.I,
        ),
        "WF3",
    ),
    (
        re.compile(
            r"\b(hooks?\b.{0,15}\bads?\b|offers?.{0,15}\bads?\b|ad hooks?|creative hooks?)\b",
            re.I,
        ),
        "WF3",
    ),
    (
        re.compile(
            r"\b(sales channel|distribution channel|pricing strateg|pricing model|customer proof|testimonial|case stud)\b",
            re.I,
        ),
        "WF3",
    ),
    (
        re.compile(
            r"\b(ideal customer profile|customer persona|buyer persona|customer segment)\b",
            re.I,
        ),
        "WF3",
    ),
    (
        re.compile(
            r"\b(brand guidelines?|brand colou?rs?|brand fonts?|brand identity|brand voice|tone of voice|brand personalit|brand position)",
            re.I,
        ),
        "WF2",
    ),
    (
        re.compile(
            r"\b(trademarks?|brand assets?|logos?|visual identity|brand book)", re.I
        ),
        "WF2",
    ),
    (
        re.compile(
            r"\b(target audience|decision.maker|competitor|competition|digital presence|social media)\b",
            re.I,
        ),
        "WF2",
    ),
    (
        re.compile(
            r"\b(photos?|videos?|media assets?|visual assets?|high.quality.{0,15}(images?|photos?|videos?))",
            re.I,
        ),
        "WF2",
    ),
    (re.compile(r"\b(unique selling|USP|differentiat)", re.I), "WF2"),
]


def _normalise(field: str) -> str:
    """Lowercase, strip, collapse whitespace/hyphens to underscores."""
    return _NORMALISE_RE.sub("_", field.strip().lower())


def resolve_field(inferred_field: str) -> tuple[str, WorkflowTarget]:
    """Resolve an LLM-inferred field name to (target_field, workflow_target).

    Known fields are normalised and looked up. Unknown fields pass through
    as-is with the default workflow target — losing an unrecognised field is
    worse than mis-routing it.
    """
    normalised = _normalise(inferred_field)
    wf = FIELD_MAP.get(normalised, DEFAULT_WORKFLOW_TARGET)
    return normalised or inferred_field.strip(), wf


def resolve_workflow_target(suggested_field: str) -> WorkflowTarget:
    """Map a suggested_field to its workflow_target (for notable facts)."""
    normalised = _normalise(suggested_field)
    return FIELD_MAP.get(normalised, DEFAULT_WORKFLOW_TARGET)


def infer_workflow_from_text(question_text: str) -> WorkflowTarget:
    """Keyword fallback when target_field is empty and workflow_target is WF1."""
    for pattern, wf in _TEXT_PATTERNS:
        if pattern.search(question_text):
            return wf
    return DEFAULT_WORKFLOW_TARGET
