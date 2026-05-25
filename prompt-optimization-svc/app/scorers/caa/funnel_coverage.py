"""Funnel coverage scorer for CAA (§5.2.2, AC-3).

New brands score lower if TOFU < 50%; established brands if BOFU < 30%.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

EXPECTED_STAGES = ("tofu", "mofu", "bofu", "retention")

# Minimum budget percentage thresholds by brand maturity
MATURITY_THRESHOLDS: dict[str, dict[str, float]] = {
    "new": {"tofu": 50.0},
    "emerging": {"tofu": 35.0},
    "established": {"bofu": 30.0},
}


def _parse_output(outputs) -> dict | None:
    if outputs is None:
        return None
    if isinstance(outputs, dict):
        return outputs
    try:
        parsed = json.loads(str(outputs))
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_stage_budgets(funnel_map: dict) -> dict[str, float]:
    """Extract stage → budget_pct mapping from funnel_map."""
    budgets: dict[str, float] = {}

    stages = funnel_map.get("stages", funnel_map)

    if isinstance(stages, list):
        for stage in stages:
            if isinstance(stage, dict):
                name = stage.get("stage", "").lower()
                try:
                    budgets[name] = float(stage.get("budget_pct", 0))
                except (TypeError, ValueError):
                    pass
    elif isinstance(stages, dict):
        for key, val in stages.items():
            if isinstance(val, dict):
                try:
                    budgets[key.lower()] = float(val.get("budget_pct", 0))
                except (TypeError, ValueError):
                    pass

    return budgets


@scorer(name="funnel_coverage")
def funnel_coverage(*, inputs, outputs, expectations=None):
    """Score funnel stage coverage based on brand maturity.

    Checks that all 4 funnel stages are present and that budget
    allocation matches maturity-appropriate thresholds.

    Args:
        inputs: Model input (unused).
        outputs: CAA response JSON with funnel_map.
        expectations: Dict with optional "brand_maturity" key
            ("new", "emerging", "established"). Defaults to "new".

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="funnel_coverage",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    funnel_map = data.get("funnel_map")
    if not isinstance(funnel_map, dict):
        return Feedback(
            name="funnel_coverage",
            value=0.0,
            rationale="Missing or invalid 'funnel_map' field.",
        )

    stage_budgets = _extract_stage_budgets(funnel_map)

    if not stage_budgets:
        return Feedback(
            name="funnel_coverage",
            value=0.0,
            rationale="No funnel stages found in funnel_map.",
        )

    # Stage presence score (50% weight)
    present = set(stage_budgets.keys()) & set(EXPECTED_STAGES)
    presence_score = len(present) / len(EXPECTED_STAGES)

    # Maturity-appropriate allocation score (50% weight)
    maturity = "new"
    if expectations and isinstance(expectations, dict):
        maturity = expectations.get("brand_maturity", "new").lower()

    thresholds = MATURITY_THRESHOLDS.get(maturity, MATURITY_THRESHOLDS["new"])
    allocation_score = 1.0

    threshold_issues = []
    for stage, min_pct in thresholds.items():
        actual = stage_budgets.get(stage, 0.0)
        if actual < min_pct:
            # Linear penalty: how far below threshold
            penalty = (min_pct - actual) / min_pct
            allocation_score -= penalty
            threshold_issues.append(f"{stage}={actual:.0f}% (need ≥{min_pct:.0f}%)")

    allocation_score = max(0.0, allocation_score)

    score = round(0.5 * presence_score + 0.5 * allocation_score, 4)

    stage_detail = ", ".join(
        f"{s}={stage_budgets.get(s, 0):.0f}%" for s in EXPECTED_STAGES
    )
    rationale = (
        f"Maturity: {maturity}. Stages: {len(present)}/4 present. "
        f"Distribution: {stage_detail}."
    )
    if threshold_issues:
        rationale += f" Below threshold: {', '.join(threshold_issues)}."

    return Feedback(
        name="funnel_coverage",
        value=score,
        rationale=rationale,
    )
