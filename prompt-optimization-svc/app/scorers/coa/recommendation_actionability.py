"""Recommendation actionability scorer for COA (§5.2.3).

Validates that each recommendation has complete, actionable fields.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

VALID_ACTION_TYPES = {
    "pause",
    "scale",
    "creative_refresh",
    "adjust_budget",
    "reallocate_budget",
}
VALID_ENTITY_TYPES = {"campaign", "ad_set", "ad"}
REQUIRED_FIELDS = (
    "action_type",
    "entity_type",
    "current_values",
    "proposed_values",
    "rationale",
)


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


@scorer(name="recommendation_actionability")
def recommendation_actionability(*, inputs, outputs, expectations=None):
    """Score whether recommendations are complete and actionable.

    Each recommendation must have action_type, entity_type,
    current_values (dict), proposed_values (dict), and rationale.

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="recommendation_actionability",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    recs = data.get("recommendations")
    if not isinstance(recs, list):
        return Feedback(
            name="recommendation_actionability",
            value=0.0,
            rationale="Missing or invalid 'recommendations' field.",
        )

    recs = [r for r in recs if isinstance(r, dict)]
    if not recs:
        return Feedback(
            name="recommendation_actionability",
            value=0.0,
            rationale="No valid recommendations found.",
        )

    actionable = 0
    issues = []

    for i, rec in enumerate(recs):
        missing = []
        for field in REQUIRED_FIELDS:
            val = rec.get(field)
            if field in ("current_values", "proposed_values"):
                if not isinstance(val, dict):
                    missing.append(field)
            elif not isinstance(val, str) or not val.strip():
                missing.append(field)

        action_type = rec.get("action_type", "")
        if action_type and action_type not in VALID_ACTION_TYPES:
            missing.append(f"invalid action_type '{action_type}'")

        entity_type = rec.get("entity_type", "")
        if entity_type and entity_type not in VALID_ENTITY_TYPES:
            missing.append(f"invalid entity_type '{entity_type}'")

        if missing:
            issues.append(f"rec[{i}]: {', '.join(missing)}")
        else:
            actionable += 1

    score = round(actionable / len(recs), 4)

    rationale = f"{actionable}/{len(recs)} recommendations are fully actionable."
    if issues:
        rationale += f" Issues: {'; '.join(issues[:3])}"
        if len(issues) > 3:
            rationale += f" (+{len(issues) - 3} more)"

    return Feedback(
        name="recommendation_actionability",
        value=score,
        rationale=rationale,
    )
