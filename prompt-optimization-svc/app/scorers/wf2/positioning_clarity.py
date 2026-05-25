"""Positioning clarity scorer for BPA (brand-positioning-agent-svc).

Checks recommended_positioning, canvas fit_score, and differentiation score.
Score = weighted: 40% positioning + 30% canvas + 30% differentiation.
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


@scorer(name="positioning_clarity")
def positioning_clarity(*, inputs, outputs, expectations=None):
    """Score positioning clarity from BPA output.

    Checks:
    - recommended_positioning: dict with non-empty 'statement' string (40%)
    - canvas: dict with 'fit_score' float 0-1 (30%)
    - differentiation: dict with 'overall_differentiation_score' (30%)

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="positioning_clarity",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    details = []
    positioning_score = 0.0
    canvas_score = 0.0
    differentiation_score = 0.0

    # 1. recommended_positioning (40%)
    rec_pos = data.get("recommended_positioning")
    if isinstance(rec_pos, dict):
        statement = rec_pos.get("statement")
        if isinstance(statement, str) and statement.strip():
            positioning_score = 1.0
            details.append("recommended_positioning.statement present")
        else:
            details.append("recommended_positioning.statement empty or not a string")
    else:
        details.append("recommended_positioning missing or not a dict")

    # 2. canvas (30%)
    canvas = data.get("canvas")
    if isinstance(canvas, dict):
        fit_score = canvas.get("fit_score")
        if isinstance(fit_score, (int, float)) and 0.0 <= float(fit_score) <= 1.0:
            canvas_score = float(fit_score)
            details.append(f"canvas.fit_score={canvas_score:.2f}")
        else:
            details.append("canvas.fit_score invalid or out of range")
    else:
        details.append("canvas missing or not a dict")

    # 3. differentiation (30%)
    diff = data.get("differentiation")
    if isinstance(diff, dict):
        overall = diff.get("overall_differentiation_score")
        if isinstance(overall, (int, float)):
            differentiation_score = min(max(float(overall), 0.0), 1.0)
            details.append(
                f"differentiation.overall_differentiation_score={differentiation_score:.2f}"
            )
        else:
            details.append("differentiation.overall_differentiation_score invalid")
    else:
        details.append("differentiation missing or not a dict")

    final_score = round(
        0.4 * positioning_score + 0.3 * canvas_score + 0.3 * differentiation_score,
        4,
    )

    return Feedback(
        name="positioning_clarity",
        value=final_score,
        rationale=f"Score {final_score:.2f}: {'; '.join(details)}",
    )
