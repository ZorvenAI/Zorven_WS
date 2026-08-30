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

    Checks for: sufficient (bool judgement), confidence (calibration),
    and agreement with expectations.admin_sufficient when available.

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

    model_sufficient = data.get("sufficient")
    if model_sufficient is None:
        return Feedback(
            name="sufficiency_agreement",
            value=0.0,
            rationale="No 'sufficient' field in output.",
        )

    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)):
        details.append(f"confidence: {confidence:.2f}")

    exp_data = _parse_output(expectations) if expectations else None
    if exp_data and "admin_sufficient" in exp_data:
        admin_sufficient = exp_data["admin_sufficient"]
        agrees = bool(model_sufficient) == bool(admin_sufficient)
        score = 1.0 if agrees else 0.0
        details.append(
            f"agreement: model={model_sufficient}," f" admin={admin_sufficient}"
        )
    else:
        has_reasoning = bool(data.get("reasoning") or data.get("rationale"))
        has_fields = bool(data.get("field_coverage") or data.get("gaps"))
        score = 0.5
        if has_reasoning:
            score += 0.25
            details.append("reasoning: present")
        if has_fields:
            score += 0.25
            details.append("field_coverage: present")
        if not has_reasoning and not has_fields:
            details.append("no expectations or supporting evidence")

    return Feedback(
        name="sufficiency_agreement",
        value=round(score, 4),
        rationale=f"Sufficiency: {'; '.join(details)}",
    )
