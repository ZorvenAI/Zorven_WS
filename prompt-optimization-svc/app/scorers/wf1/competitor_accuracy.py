"""Competitor accuracy scorer for CIA (WF1).

Checks CIA output for competitors (list of dicts with market_position),
positioning_gaps (non-empty list), and benchmarking_report (dict).
Score = checks passed / 3.
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


@scorer(name="competitor_accuracy")
def competitor_accuracy(*, inputs, outputs, expectations=None):
    """Score CIA output accuracy.

    Checks for three key components: competitors (list of dicts each with
    market_position), positioning_gaps (non-empty list), and
    benchmarking_report (dict).

    Returns:
        Feedback with value 0.0-1.0 (checks passed / 3).
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="competitor_accuracy",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    passed = 0
    details = []

    # Check competitors list with market_position in each
    competitors = data.get("competitors")
    if isinstance(competitors, list) and len(competitors) > 0:
        with_position = sum(
            1
            for c in competitors
            if isinstance(c, dict) and c.get("market_position") is not None
        )
        if with_position == len(competitors):
            passed += 1
            details.append(
                f"competitors: {len(competitors)} entries, all have market_position"
            )
        else:
            details.append(
                f"competitors: {with_position}/{len(competitors)} have market_position"
            )
    else:
        details.append("competitors: missing or empty")

    # Check positioning_gaps
    positioning_gaps = data.get("positioning_gaps")
    if isinstance(positioning_gaps, list) and len(positioning_gaps) > 0:
        passed += 1
        details.append(f"positioning_gaps: {len(positioning_gaps)} items")
    else:
        details.append("positioning_gaps: missing or empty")

    # Check benchmarking_report
    benchmarking_report = data.get("benchmarking_report")
    if isinstance(benchmarking_report, dict):
        passed += 1
        details.append("benchmarking_report: present")
    else:
        details.append("benchmarking_report: missing or not a dict")

    score = passed / 3.0

    return Feedback(
        name="competitor_accuracy",
        value=score,
        rationale=f"{passed}/3 checks passed. {'; '.join(details)}",
    )
