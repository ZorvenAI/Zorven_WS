"""Data grounding scorer for COA (§5.2.3, AC-2).

Rejects fabricated numbers — all recommendations must cite input metrics.
"""

import json
import logging
import re

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

# Pattern to detect numeric citations in rationale text
NUMBER_PATTERN = re.compile(r"\d+\.?\d*")


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


def _has_numeric_metrics(values: dict) -> bool:
    """Check if current_values contains at least one numeric metric."""
    for v in values.values():
        if isinstance(v, (int, float)):
            return True
    return False


def _extract_numbers(text: str) -> set[float]:
    """Extract all numeric values from text."""
    return {float(m) for m in NUMBER_PATTERN.findall(text)}


def _rationale_cites_metrics(rationale: str, metrics: dict) -> bool:
    """Check if rationale cites numbers that match current_values metrics.

    At least one number in the rationale must match (within 0.5% tolerance)
    a numeric value from current_values to count as grounded.
    """
    rationale_numbers = _extract_numbers(rationale)
    if not rationale_numbers:
        return False

    metric_values = {float(v) for v in metrics.values() if isinstance(v, (int, float))}
    if not metric_values:
        return False

    for rn in rationale_numbers:
        for mv in metric_values:
            if mv == 0:
                if rn == 0:
                    return True
            elif abs(rn - mv) / abs(mv) <= 0.005:
                return True
    return False


@scorer(name="data_grounding")
def data_grounding(*, inputs, outputs, expectations=None):
    """Score whether recommendations are grounded in real metrics.

    Each recommendation must have current_values with numeric metrics,
    and its rationale should cite specific numbers.

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="data_grounding",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    recs = data.get("recommendations")
    if not isinstance(recs, list):
        return Feedback(
            name="data_grounding",
            value=0.0,
            rationale="Missing or invalid 'recommendations' field.",
        )

    recs = [r for r in recs if isinstance(r, dict)]
    if not recs:
        return Feedback(
            name="data_grounding",
            value=0.0,
            rationale="No valid recommendations found.",
        )

    grounded = 0
    issues = []

    for i, rec in enumerate(recs):
        current = rec.get("current_values")
        rationale = rec.get("rationale", "")

        has_metrics = isinstance(current, dict) and _has_numeric_metrics(current)
        cites_actual = (
            isinstance(current, dict)
            and isinstance(rationale, str)
            and _rationale_cites_metrics(rationale, current)
        )

        if has_metrics and cites_actual:
            grounded += 1
        elif has_metrics:
            # Metrics present but rationale cites unrelated/no numbers — partial
            grounded += 0.5
            issues.append(
                f"rec[{i}]: rationale numbers don't match current_values metrics"
            )
        else:
            issues.append(f"rec[{i}]: missing numeric metrics in current_values")

    score = round(grounded / len(recs), 4)

    rationale_text = f"{grounded:.1f}/{len(recs)} recommendations grounded in data."
    if issues:
        rationale_text += f" Issues: {'; '.join(issues[:3])}"
        if len(issues) > 3:
            rationale_text += f" (+{len(issues) - 3} more)"

    return Feedback(
        name="data_grounding",
        value=score,
        rationale=rationale_text,
    )
