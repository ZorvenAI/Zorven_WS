"""VoCA sentiment scorer (WF1).

Checks VoCA output for sentiment (dict with overall_sentiment),
nps_analysis (dict), and pain_point_priority_matrix (dict or list).
Score = components present / 3.
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


@scorer(name="voca_sentiment")
def voca_sentiment(*, inputs, outputs, expectations=None):
    """Score VoCA output sentiment completeness.

    Checks for three components: sentiment (dict with overall_sentiment),
    nps_analysis (dict), and pain_point_priority_matrix (dict or list).

    Returns:
        Feedback with value 0.0-1.0 (components present / 3).
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="voca_sentiment",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    present = 0
    details = []

    # Check sentiment with overall_sentiment
    sentiment = data.get("sentiment")
    if isinstance(sentiment, dict) and sentiment.get("overall_sentiment") is not None:
        present += 1
        details.append(
            f"sentiment: present, overall_sentiment={sentiment['overall_sentiment']}"
        )
    else:
        details.append("sentiment: missing, not a dict, or lacks overall_sentiment")

    # Check nps_analysis
    nps_analysis = data.get("nps_analysis")
    if isinstance(nps_analysis, dict):
        present += 1
        details.append("nps_analysis: present")
    else:
        details.append("nps_analysis: missing or not a dict")

    # Check pain_point_priority_matrix (dict or list)
    matrix = data.get("pain_point_priority_matrix")
    if isinstance(matrix, (dict, list)):
        if isinstance(matrix, list) and len(matrix) == 0:
            details.append("pain_point_priority_matrix: empty list")
        else:
            present += 1
            details.append("pain_point_priority_matrix: present")
    else:
        details.append("pain_point_priority_matrix: missing or invalid type")

    score = present / 3.0

    return Feedback(
        name="voca_sentiment",
        value=round(score, 4),
        rationale=f"{present}/3 components present. {'; '.join(details)}",
    )
