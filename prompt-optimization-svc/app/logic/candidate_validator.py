"""Candidate validation against held-out golden dataset (§4.1 Step 5).

Compares GEPA candidate aggregate scorer scores to current PRODUCTION
prompt. Only candidates exceeding OPT-03 (5% improvement) proceed
to canary. Individual scorer regressions > OPT-04 (3%) trigger
PENDING_APPROVAL for human review.
"""

import logging
import random
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

VALID_DECISIONS = ("CANARY", "REJECTED", "PENDING_APPROVAL")


@dataclass
class ValidationResult:
    """Result of candidate validation against production."""

    passed: bool = False
    decision: str = "REJECTED"
    aggregate_improvement: float = 0.0
    scorer_regressions: dict[str, float] = field(default_factory=dict)
    candidate_scores: dict[str, float] = field(default_factory=dict)
    production_scores: dict[str, float] = field(default_factory=dict)
    held_out_count: int = 0


def split_holdout(
    examples: list,
    holdout_pct: float = 0.2,
    seed: int = 42,
) -> tuple[list, list]:
    """Split examples into train and holdout sets.

    Uses a deterministic shuffle for reproducibility.

    Args:
        examples: Full list of examples.
        holdout_pct: Fraction to hold out (default 20%, AC-1).
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (train, holdout) lists.
    """
    if not examples:
        return [], []

    shuffled = list(examples)
    rng = random.Random(seed)
    rng.shuffle(shuffled)

    holdout_count = max(1, int(len(shuffled) * holdout_pct))
    holdout = shuffled[:holdout_count]
    train = shuffled[holdout_count:]

    return train, holdout


def compute_aggregate_score(scores: dict[str, float]) -> float:
    """Compute mean aggregate score across all scorers.

    Args:
        scores: Dict of scorer_name → score (0.0-1.0).

    Returns:
        Mean score, or 0.0 if empty.
    """
    if not scores:
        return 0.0
    return sum(scores.values()) / len(scores)


def validate_candidate(
    candidate_scores: dict[str, float],
    production_scores: dict[str, float],
    improvement_threshold: float = 0.05,
    regression_threshold: float = 0.03,
) -> ValidationResult:
    """Validate a GEPA candidate against current production scores.

    Args:
        candidate_scores: Per-scorer scores for the candidate.
        production_scores: Per-scorer scores for current production.
        improvement_threshold: Min aggregate improvement (OPT-03, default 5%).
        regression_threshold: Max individual regression (OPT-04, default 3%).

    Returns:
        ValidationResult with decision: CANARY, REJECTED, or PENDING_APPROVAL.
    """
    candidate_agg = compute_aggregate_score(candidate_scores)
    production_agg = compute_aggregate_score(production_scores)

    # Compute aggregate improvement
    if production_agg > 0:
        improvement = (candidate_agg - production_agg) / production_agg
    elif candidate_agg > 0:
        improvement = 1.0  # Infinite improvement from zero
    else:
        improvement = 0.0

    # AC-2: Check aggregate improvement threshold (OPT-03)
    if improvement < improvement_threshold:
        logger.info(
            "Candidate REJECTED: aggregate improvement %.2f%% < %.2f%% threshold",
            improvement * 100,
            improvement_threshold * 100,
        )
        return ValidationResult(
            passed=False,
            decision="REJECTED",
            aggregate_improvement=improvement,
            candidate_scores=candidate_scores,
            production_scores=production_scores,
        )

    # AC-3: Check individual scorer regressions (OPT-04)
    regressions: dict[str, float] = {}
    common_scorers = set(candidate_scores.keys()) & set(production_scores.keys())
    for scorer_name in common_scorers:
        prod_score = production_scores[scorer_name]
        cand_score = candidate_scores[scorer_name]
        if prod_score > 0:
            regression = (prod_score - cand_score) / prod_score
            if regression > regression_threshold:
                regressions[scorer_name] = regression

    if regressions:
        logger.warning(
            "Candidate PENDING_APPROVAL: %d scorer regressions > %.0f%% — %s",
            len(regressions),
            regression_threshold * 100,
            ", ".join(f"{k}: -{v * 100:.1f}%" for k, v in sorted(regressions.items())),
        )
        return ValidationResult(
            passed=False,
            decision="PENDING_APPROVAL",
            aggregate_improvement=improvement,
            scorer_regressions=regressions,
            candidate_scores=candidate_scores,
            production_scores=production_scores,
        )

    # Passed all checks — proceed to canary
    logger.info(
        "Candidate approved for CANARY: aggregate improvement %.2f%%",
        improvement * 100,
    )
    return ValidationResult(
        passed=True,
        decision="CANARY",
        aggregate_improvement=improvement,
        candidate_scores=candidate_scores,
        production_scores=production_scores,
    )
