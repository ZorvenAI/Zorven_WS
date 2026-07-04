"""CAA campaign architecture scorers (§5.2.2)."""

from app.scorers.caa.budget_rationality import budget_rationality
from app.scorers.caa.funnel_coverage import funnel_coverage
from app.scorers.caa.structure_validity import structure_validity
from app.scorers.caa.targeting_quality import targeting_quality

CAA_SCORERS = [
    structure_validity,
    budget_rationality,
    funnel_coverage,
    targeting_quality,
]

__all__ = [
    "CAA_SCORERS",
    "structure_validity",
    "budget_rationality",
    "funnel_coverage",
    "targeting_quality",
]
