"""COA continuous optimization scorers (§5.2.3)."""

from app.scorers.coa.data_grounding import data_grounding
from app.scorers.coa.guardrail_compliance import guardrail_compliance
from app.scorers.coa.prioritization_quality import prioritization_quality
from app.scorers.coa.recommendation_actionability import recommendation_actionability

COA_SCORERS = [
    recommendation_actionability,
    guardrail_compliance,
    data_grounding,
    prioritization_quality,
]

__all__ = [
    "COA_SCORERS",
    "recommendation_actionability",
    "guardrail_compliance",
    "data_grounding",
    "prioritization_quality",
]
