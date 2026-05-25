"""Prioritization quality scorer for COA (§5.2.3, AC-3).

Kill/pause actions must be ranked before scale actions when both present.
High priority must appear before medium priority.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

# Action types considered "kill" (should come first)
KILL_ACTIONS = {"pause"}
# Action types considered "scale" (should come after kill)
SCALE_ACTIONS = {"scale", "adjust_budget", "reallocate_budget"}

PRIORITY_ORDER = {"high": 0, "medium": 1}


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


@scorer(name="prioritization_quality")
def prioritization_quality(*, inputs, outputs, expectations=None):
    """Score recommendation prioritization ordering.

    Kill/pause actions should appear before scale actions.
    High priority should appear before medium priority.

    Score = 50% action-type ordering + 50% priority ordering.

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="prioritization_quality",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    recs = data.get("recommendations")
    if not isinstance(recs, list):
        return Feedback(
            name="prioritization_quality",
            value=0.0,
            rationale="Missing or invalid 'recommendations' field.",
        )

    recs = [r for r in recs if isinstance(r, dict)]
    if not recs:
        return Feedback(
            name="prioritization_quality",
            value=0.0,
            rationale="No valid recommendations found.",
        )

    if len(recs) == 1:
        return Feedback(
            name="prioritization_quality",
            value=1.0,
            rationale="Single recommendation — ordering is trivially correct.",
        )

    # Check action-type ordering: kill before scale
    last_kill_idx = -1
    first_scale_idx = len(recs)
    has_kill = False
    has_scale = False

    for i, rec in enumerate(recs):
        action = rec.get("action_type", "")
        if action in KILL_ACTIONS:
            last_kill_idx = i
            has_kill = True
        if action in SCALE_ACTIONS and not has_scale:
            first_scale_idx = i
            has_scale = True

    if has_kill and has_scale:
        action_order_score = 1.0 if last_kill_idx < first_scale_idx else 0.0
    else:
        action_order_score = 1.0  # No conflict when only one type present

    # Check priority ordering: high before medium
    last_high_idx = -1
    first_medium_idx = len(recs)
    has_high = False
    has_medium = False

    for i, rec in enumerate(recs):
        priority = rec.get("priority", "medium")
        if priority == "high":
            last_high_idx = i
            has_high = True
        if priority == "medium" and not has_medium:
            first_medium_idx = i
            has_medium = True

    if has_high and has_medium:
        priority_order_score = 1.0 if last_high_idx < first_medium_idx else 0.0
    else:
        priority_order_score = 1.0

    score = round(0.5 * action_order_score + 0.5 * priority_order_score, 4)

    details = []
    if has_kill and has_scale:
        order = "correct" if action_order_score == 1.0 else "WRONG"
        details.append(f"kill-before-scale: {order}")
    if has_high and has_medium:
        order = "correct" if priority_order_score == 1.0 else "WRONG"
        details.append(f"high-before-medium: {order}")

    rationale = f"{len(recs)} recommendations. "
    if details:
        rationale += "; ".join(details) + "."
    else:
        rationale += "No ordering conflicts (single action/priority type)."

    return Feedback(
        name="prioritization_quality",
        value=score,
        rationale=rationale,
    )
