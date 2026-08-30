"""Media analysis accuracy scorer for OIA (§17.1).

Checks caption quality, doc_type classification, and
sensitivity_class assignment against admin corrections.
Used for both single-frame and multi-frame media analysis prompts.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

_VALID_DOC_TYPES = {
    "invoice",
    "receipt",
    "contract",
    "id_card",
    "passport",
    "business_card",
    "presentation",
    "report",
    "letter",
    "form",
    "photo",
    "screenshot",
    "other",
}
_VALID_SENSITIVITY = {"GENERAL", "IDENTITY", "FINANCIAL"}


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


@scorer(name="media_analysis_accuracy")
def media_analysis_accuracy(*, inputs, outputs, expectations=None):
    """Score media analysis classification accuracy.

    Prompt output keys: caption (str), doc_type (str),
    sensitivity_class (str).

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="media_analysis_accuracy",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    score_parts = 0.0
    total_parts = 3
    details = []

    caption = data.get("caption", "")
    if isinstance(caption, str) and caption.strip():
        score_parts += 1
        details.append(f"caption: {len(caption)} chars")
    else:
        details.append("caption: missing or empty")

    doc_type = data.get("doc_type", "")
    if isinstance(doc_type, str) and doc_type in _VALID_DOC_TYPES:
        score_parts += 1
        details.append(f"doc_type: {doc_type}")
    elif isinstance(doc_type, str) and doc_type:
        score_parts += 0.5
        details.append(f"doc_type: '{doc_type}' not in enum")
    else:
        details.append("doc_type: missing")

    sensitivity = data.get("sensitivity_class", "")
    if isinstance(sensitivity, str) and sensitivity in _VALID_SENSITIVITY:
        score_parts += 1
        details.append(f"sensitivity_class: {sensitivity}")
    elif isinstance(sensitivity, str) and sensitivity:
        score_parts += 0.5
        details.append(f"sensitivity_class: '{sensitivity}' not in enum")
    else:
        details.append("sensitivity_class: missing")

    exp_data = _parse_output(expectations) if expectations else None
    if exp_data:
        exp_doc = exp_data.get("doc_type")
        exp_sens = exp_data.get("sensitivity_class")
        if exp_doc and doc_type != exp_doc:
            score_parts -= 0.5
            details.append(f"doc_type mismatch: expected {exp_doc}")
        if exp_sens and sensitivity != exp_sens:
            score_parts -= 0.5
            details.append(f"sensitivity mismatch: expected {exp_sens}")

    score = max(0.0, score_parts / total_parts)

    return Feedback(
        name="media_analysis_accuracy",
        value=round(score, 4),
        rationale=f"Media accuracy: {'; '.join(details)}",
    )
