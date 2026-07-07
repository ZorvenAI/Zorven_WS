"""Individual baseline scorer generators (US-054).

Each function creates a scorer callable that validates a specific aspect
of agent output against a SkillOutputField constraint. Scorers follow
the MLflow GEPA protocol: accept (inputs, outputs, expectations) kwargs,
return Feedback with value 0.0-1.0 and rationale.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from mlflow.entities.assessment import Feedback

logger = logging.getLogger(__name__)


def _parse_json_output(outputs) -> tuple[Optional[dict], Optional[str]]:
    """Parse outputs as JSON dict. Returns (parsed, error_rationale)."""
    if outputs is None:
        return None, "Output is None."
    text = str(outputs).strip()
    if not text:
        return None, "Output is empty."
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return None, f"Output is JSON but not a dict (got {type(parsed).__name__})."
        return parsed, None
    except json.JSONDecodeError as exc:
        return None, f"Output is not valid JSON: {exc.msg}."


def make_field_presence_scorer(field_name: str, skill_id: str) -> Callable:
    """Create a scorer that checks if a required field exists in JSON output."""
    scorer_name = f"baseline_{skill_id}_presence_{field_name}"

    def score(*, inputs, outputs, expectations=None):
        parsed, error = _parse_json_output(outputs)
        if parsed is None:
            return Feedback(name=scorer_name, value=0.0, rationale=error)

        if field_name in parsed:
            return Feedback(
                name=scorer_name,
                value=1.0,
                rationale=f"Required field '{field_name}' is present.",
            )
        return Feedback(
            name=scorer_name,
            value=0.0,
            rationale=f"Required field '{field_name}' is missing from output.",
        )

    score.__name__ = scorer_name
    return score


def make_max_length_scorer(field_name: str, max_length: int, skill_id: str) -> Callable:
    """Create a scorer that checks string field length <= max_length.

    Returns 1.0 if within limit. If over, returns a proportional score
    (max_length / actual_length) clamped to [0.0, 1.0].
    Returns 1.0 if the field is missing (presence is checked separately).
    """
    scorer_name = f"baseline_{skill_id}_maxlen_{field_name}"

    def score(*, inputs, outputs, expectations=None):
        parsed, error = _parse_json_output(outputs)
        if parsed is None:
            return Feedback(name=scorer_name, value=0.0, rationale=error)

        if field_name not in parsed:
            return Feedback(
                name=scorer_name,
                value=1.0,
                rationale=f"Field '{field_name}' not present — length check skipped.",
            )

        value = parsed[field_name]
        if not isinstance(value, str):
            value = json.dumps(value)

        actual_length = len(value)
        if actual_length <= max_length:
            return Feedback(
                name=scorer_name,
                value=1.0,
                rationale=(
                    f"Field '{field_name}' length {actual_length} "
                    f"is within limit {max_length}."
                ),
            )

        proportional = max_length / actual_length
        return Feedback(
            name=scorer_name,
            value=round(proportional, 4),
            rationale=(
                f"Field '{field_name}' length {actual_length} "
                f"exceeds limit {max_length}."
            ),
        )

    score.__name__ = scorer_name
    return score


def make_enum_compliance_scorer(
    field_name: str, allowed_values: list[str], skill_id: str
) -> Callable:
    """Create a scorer that checks field value is in allowed enum_values."""
    scorer_name = f"baseline_{skill_id}_enum_{field_name}"
    allowed_set = set(allowed_values)

    def score(*, inputs, outputs, expectations=None):
        parsed, error = _parse_json_output(outputs)
        if parsed is None:
            return Feedback(name=scorer_name, value=0.0, rationale=error)

        if field_name not in parsed:
            return Feedback(
                name=scorer_name,
                value=0.0,
                rationale=f"Field '{field_name}' is missing from output.",
            )

        value = str(parsed[field_name])
        if value in allowed_set:
            return Feedback(
                name=scorer_name,
                value=1.0,
                rationale=(
                    f"Field '{field_name}' value '{value}' " f"is in allowed values."
                ),
            )
        return Feedback(
            name=scorer_name,
            value=0.0,
            rationale=(
                f"Field '{field_name}' value '{value}' "
                f"is not in allowed values: {sorted(allowed_values)}."
            ),
        )

    score.__name__ = scorer_name
    return score


def make_schema_completeness_scorer(
    required_fields: list[str], skill_id: str
) -> Callable:
    """Create a scorer that returns fraction of required fields present."""
    scorer_name = f"baseline_{skill_id}_schema_completeness"

    def score(*, inputs, outputs, expectations=None):
        parsed, error = _parse_json_output(outputs)
        if parsed is None:
            return Feedback(name=scorer_name, value=0.0, rationale=error)

        if not required_fields:
            return Feedback(
                name=scorer_name,
                value=1.0,
                rationale="No required fields defined — trivially complete.",
            )

        present = sum(1 for f in required_fields if f in parsed)
        total = len(required_fields)
        value = round(present / total, 4)
        missing = [f for f in required_fields if f not in parsed]

        if present == total:
            return Feedback(
                name=scorer_name,
                value=1.0,
                rationale=f"All {total} required fields present.",
            )
        return Feedback(
            name=scorer_name,
            value=value,
            rationale=(
                f"{present}/{total} required fields present. " f"Missing: {missing}."
            ),
        )

    score.__name__ = scorer_name
    return score
