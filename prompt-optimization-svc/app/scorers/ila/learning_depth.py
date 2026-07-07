"""Learning depth scorer for ILA (Intelligence Loop Agent).

Evaluates the depth and quality of extracted learnings by checking
confidence thresholds and contradiction detection thoroughness.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

VALID_IMPACT_VALUES = {"HIGH", "MEDIUM", "LOW"}


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


@scorer(name="learning_depth")
def learning_depth(*, inputs, outputs, expectations=None):
    """Score the depth and quality of ILA learning extraction.

    Checks `learnings` (list of dicts with `confidence` int 0-100 and
    `impact` string HIGH/MEDIUM/LOW) and `contradictions` (list).

    Score = ratio of learnings with confidence >= 50 to total learnings.
    Contradiction detection is a bonus showing thoroughness.
    Returns 0.0 if no learnings are present.

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="learning_depth",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    learnings = data.get("learnings")
    if not isinstance(learnings, list):
        return Feedback(
            name="learning_depth",
            value=0.0,
            rationale="Missing or invalid 'learnings' field.",
        )

    if not learnings:
        return Feedback(
            name="learning_depth",
            value=0.0,
            rationale="Empty learnings list.",
        )

    # Count valid learnings with confidence >= 50
    total = 0
    confident = 0
    for learning in learnings:
        if not isinstance(learning, dict):
            continue
        total += 1

        confidence = learning.get("confidence")
        if not isinstance(confidence, int):
            continue

        impact = learning.get("impact")
        if not isinstance(impact, str) or impact not in VALID_IMPACT_VALUES:
            continue

        if confidence >= 50:
            confident += 1

    if total == 0:
        return Feedback(
            name="learning_depth",
            value=0.0,
            rationale="No valid learning dicts found in learnings list.",
        )

    base_score = confident / total

    # Contradiction detection bonus (shows thoroughness)
    contradictions = data.get("contradictions")
    bonus_note = ""
    if isinstance(contradictions, list) and len(contradictions) > 0:
        bonus_note = (
            f" Contradictions detected ({len(contradictions)})"
            " — shows analytical thoroughness."
        )

    return Feedback(
        name="learning_depth",
        value=round(base_score, 4),
        rationale=(
            f"{confident}/{total} learnings have confidence >= 50." f"{bonus_note}"
        ),
    )
