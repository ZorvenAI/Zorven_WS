"""Targeting quality scorer for CAA (§5.2.2, AC-4).

Targeting must include demographics, interests, and a custom/lookalike audience.
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


def _has_demographics(spec: dict) -> bool:
    """Check for non-empty demographics dict."""
    demo = spec.get("demographics")
    return isinstance(demo, dict) and len(demo) > 0


def _has_interests(spec: dict) -> bool:
    """Check for non-empty interests list."""
    interests = spec.get("interests")
    return isinstance(interests, list) and len(interests) > 0


def _has_custom_or_lookalike(spec: dict) -> bool:
    """Check for at least one custom or lookalike audience."""
    custom = spec.get("custom_audiences")
    lookalike = spec.get("lookalike_audiences")
    has_custom = isinstance(custom, list) and len(custom) > 0
    has_lookalike = isinstance(lookalike, list) and len(lookalike) > 0
    return has_custom or has_lookalike


@scorer(name="targeting_quality")
def targeting_quality(*, inputs, outputs, expectations=None):
    """Score audience targeting completeness.

    Each targeting spec is checked for demographics, interests,
    and custom/lookalike audiences. Score = ratio of specs
    meeting all 3 criteria.

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="targeting_quality",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    specs = data.get("targeting_specs")
    if not isinstance(specs, list):
        return Feedback(
            name="targeting_quality",
            value=0.0,
            rationale="Missing or invalid 'targeting_specs' field.",
        )

    specs = [s for s in specs if isinstance(s, dict)]
    if not specs:
        return Feedback(
            name="targeting_quality",
            value=0.0,
            rationale="No valid targeting specs found.",
        )

    complete = 0
    issues = []

    for i, spec in enumerate(specs):
        has_demo = _has_demographics(spec)
        has_int = _has_interests(spec)
        has_aud = _has_custom_or_lookalike(spec)

        if has_demo and has_int and has_aud:
            complete += 1
        else:
            missing = []
            if not has_demo:
                missing.append("demographics")
            if not has_int:
                missing.append("interests")
            if not has_aud:
                missing.append("custom/lookalike")
            name = spec.get("ad_set_name", f"spec[{i}]")
            issues.append(f"{name}: missing {', '.join(missing)}")

    score = round(complete / len(specs), 4)

    rationale = f"{complete}/{len(specs)} targeting specs fully complete."
    if issues:
        rationale += f" Issues: {'; '.join(issues[:3])}"
        if len(issues) > 3:
            rationale += f" (+{len(issues) - 3} more)"

    return Feedback(
        name="targeting_quality",
        value=score,
        rationale=rationale,
    )
