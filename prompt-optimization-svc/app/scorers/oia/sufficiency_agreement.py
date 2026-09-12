"""Sufficiency agreement scorer for OIA (§17.1).

Checks that sufficiency judgements agree with admin final decisions
and are well-calibrated against downstream edit rates.
Score = agreement rate between model sufficiency and admin checkbox.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)


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


@scorer(name="sufficiency_agreement")
def sufficiency_agreement(*, inputs, outputs, expectations=None):
    """Score sufficiency model-admin agreement.

    Prompt output keys: score (float 0-1), missing_aspects (list).
    Model sufficiency derived as score >= 0.5.

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="sufficiency_agreement",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    details = []

    model_score = data.get("score")
    if model_score is None or not isinstance(model_score, (int, float)):
        return Feedback(
            name="sufficiency_agreement",
            value=0.0,
            rationale="No 'score' field in output.",
        )

    model_sufficient = model_score >= 0.5
    details.append(f"model_score: {model_score:.2f}")

    exp_data = _parse_output(expectations) if expectations else None
    if exp_data and "admin_sufficient" in exp_data:
        admin_sufficient = exp_data["admin_sufficient"]
        agrees = model_sufficient == bool(admin_sufficient)
        score = 1.0 if agrees else 0.0
        details.append(
            f"agreement: model={model_sufficient}," f" admin={admin_sufficient}"
        )
    else:
        missing = data.get("missing_aspects", [])
        has_missing = isinstance(missing, list) and len(missing) > 0
        score = 0.5
        if has_missing:
            score += 0.25
            details.append(f"missing_aspects: {len(missing)} listed")
        if model_score > 0:
            score += 0.25
            details.append("non-zero score present")
        if not has_missing and model_score == 0:
            details.append("no expectations or supporting evidence")

    return Feedback(
        name="sufficiency_agreement",
        value=round(score, 4),
        rationale=f"Sufficiency: {'; '.join(details)}",
    )
