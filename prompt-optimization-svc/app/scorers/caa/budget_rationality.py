"""Budget rationality scorer for CAA (§5.2.2, AC-2).

Budget allocations must sum to 100% (±1% tolerance).
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

TOLERANCE = 1.0  # ±1% acceptable deviation
MAX_DEVIATION = 10.0  # >10% off → score 0.0


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


@scorer(name="budget_rationality")
def budget_rationality(*, inputs, outputs, expectations=None):
    """Score whether budget allocations sum to 100%.

    Extracts budget_pct from funnel_map stages and validates
    they sum to 100% within ±1% tolerance.

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="budget_rationality",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    funnel_map = data.get("funnel_map")
    if not isinstance(funnel_map, dict):
        return Feedback(
            name="budget_rationality",
            value=0.0,
            rationale="Missing or invalid 'funnel_map' field.",
        )

    # Extract budget percentages from funnel stages
    stages = funnel_map.get("stages")
    if not stages:
        # Try funnel_map directly as stage dict
        stages = funnel_map

    budget_pcts = []
    if isinstance(stages, list):
        for stage in stages:
            if isinstance(stage, dict):
                pct = stage.get("budget_pct", 0)
                try:
                    budget_pcts.append(float(pct))
                except (TypeError, ValueError):
                    pass
    elif isinstance(stages, dict):
        for key, val in stages.items():
            if isinstance(val, dict):
                pct = val.get("budget_pct", 0)
                try:
                    budget_pcts.append(float(pct))
                except (TypeError, ValueError):
                    pass
            elif isinstance(val, (int, float)):
                budget_pcts.append(float(val))

    if not budget_pcts:
        return Feedback(
            name="budget_rationality",
            value=0.0,
            rationale="No budget percentages found in funnel_map.",
        )

    total = sum(budget_pcts)
    deviation = abs(total - 100.0)

    if deviation <= TOLERANCE:
        score = 1.0
    elif deviation >= MAX_DEVIATION:
        score = 0.0
    else:
        score = round(1.0 - (deviation - TOLERANCE) / (MAX_DEVIATION - TOLERANCE), 4)

    return Feedback(
        name="budget_rationality",
        value=score,
        rationale=(
            f"Budget sum: {total:.1f}% (deviation: {deviation:.1f}%). "
            f"Stages: {len(budget_pcts)}. "
            f"{'Within' if deviation <= TOLERANCE else 'Outside'} ±{TOLERANCE}% tolerance."
        ),
    )
