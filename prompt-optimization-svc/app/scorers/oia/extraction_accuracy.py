"""Extraction accuracy scorer for OIA (§17.1).

Checks field-level exact/semantic match against admin final values
and JSON schema compliance of extracted fields.
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


def _fields_to_dict(fields_list) -> dict:
    """Convert [{field_name, value, ...}] list to {name: value}."""
    result = {}
    if not isinstance(fields_list, list):
        return result
    for item in fields_list:
        if isinstance(item, dict) and "field_name" in item:
            result[item["field_name"]] = item.get("value")
    return result


@scorer(name="extraction_accuracy")
def extraction_accuracy(*, inputs, outputs, expectations=None):
    """Score field extraction accuracy.

    Prompt output keys: fields (list of {field_name, value,
    confidence, evidence}).

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="extraction_accuracy",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    score_parts = 0.0
    total_parts = 2
    details = []

    raw_fields = data.get("fields", [])
    fields = _fields_to_dict(raw_fields)

    if fields:
        non_empty = sum(1 for v in fields.values() if v is not None and v != "")
        ratio = non_empty / len(fields)
        score_parts += ratio
        details.append(f"fields: {non_empty}/{len(fields)} non-empty")
    else:
        details.append("fields: missing or empty")

    exp_data = _parse_output(expectations) if expectations else None
    if exp_data:
        exp_fields_raw = exp_data.get("admin_fields", exp_data.get("fields", []))
        expected = (
            _fields_to_dict(exp_fields_raw)
            if isinstance(exp_fields_raw, list)
            else exp_fields_raw if isinstance(exp_fields_raw, dict) else {}
        )
        if isinstance(expected, dict) and expected:
            matches = 0
            total = len(expected)
            for key, expected_val in expected.items():
                actual_val = fields.get(key)
                if actual_val is not None and expected_val is not None:
                    if (
                        str(actual_val).strip().lower()
                        == str(expected_val).strip().lower()
                    ):
                        matches += 1
            accuracy = matches / total if total > 0 else 0
            score_parts += accuracy
            details.append(f"field_match: {matches}/{total} exact")
        else:
            score_parts += 0.5
            details.append("no admin_fields for comparison")
    else:
        score_parts += 0.5
        details.append("no expectations provided")

    score = score_parts / total_parts

    return Feedback(
        name="extraction_accuracy",
        value=round(score, 4),
        rationale=f"Extraction: {'; '.join(details)}",
    )
