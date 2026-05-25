"""Scorer library for GEPA prompt optimization (§5.1, §5.2)."""

from app.scorers.coa import (
    COA_SCORERS,
    data_grounding,
    guardrail_compliance,
    prioritization_quality,
    recommendation_actionability,
)
from app.scorers.caa import (
    CAA_SCORERS,
    budget_rationality,
    funnel_coverage,
    structure_validity,
    targeting_quality,
)
from app.scorers.cga import (
    CGA_SCORERS,
    brand_voice_match,
    character_limits,
    creative_compliance,
    cta_effectiveness,
    variant_diversity,
)
from app.scorers.common import (
    brand_voice,
    json_compliance,
    pii_safety,
    token_efficiency,
)

COMMON_SCORERS = [json_compliance, pii_safety, token_efficiency, brand_voice]

__all__ = [
    "COMMON_SCORERS",
    "CGA_SCORERS",
    "CAA_SCORERS",
    "COA_SCORERS",
    "json_compliance",
    "pii_safety",
    "token_efficiency",
    "brand_voice",
    "creative_compliance",
    "character_limits",
    "variant_diversity",
    "brand_voice_match",
    "cta_effectiveness",
    "structure_validity",
    "budget_rationality",
    "funnel_coverage",
    "targeting_quality",
    "recommendation_actionability",
    "guardrail_compliance",
    "data_grounding",
    "prioritization_quality",
]
