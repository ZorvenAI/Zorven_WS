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
    "brand_personality": "WF2",
    "brand_positioning": "WF2",
    "differentiation": "WF2",
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
    "campaigns": "WF3",
    "advertising": "WF3",
    "retail_locations": "WF3",
    "stores": "WF3",
    "partnerships": "WF3",
}

_NORMALISE_RE = re.compile(r"[\s\-]+")

DEFAULT_WORKFLOW_TARGET: Final[WorkflowTarget] = "WF1"


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
