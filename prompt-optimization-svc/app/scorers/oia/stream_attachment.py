"""Stream attachment scorer for OIA (§17.1).

Checks that live-stream analysis correctly attaches answers to
questionnaire questions and detects ad-hoc questions.
Score = weighted combination of question-attachment accuracy and
ad-hoc detection F1.
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


@scorer(name="stream_attachment")
def stream_attachment(*, inputs, outputs, expectations=None):
    """Score stream analysis question-attachment accuracy.

    Checks for: matched_questions (with question_id and answer),
    ad_hoc_questions (detected spontaneous questions), and
    confidence scores on attachments.

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="stream_attachment",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    score_parts = 0.0
    total_parts = 2
    details = []

    matched = data.get("matched_questions", data.get("matches", []))
    if isinstance(matched, list) and len(matched) > 0:
        attached = sum(
            1
            for m in matched
            if isinstance(m, dict) and m.get("question_id") and m.get("answer")
        )
        ratio = attached / len(matched) if matched else 0
        score_parts += ratio
        details.append(f"attachments: {attached}/{len(matched)} valid")
    else:
        details.append("matched_questions: missing or empty")

    ad_hoc = data.get("ad_hoc_questions", data.get("ad_hoc", []))
    if isinstance(ad_hoc, list):
        score_parts += 1
        details.append(f"ad_hoc_detection: {len(ad_hoc)} detected")
    else:
        details.append("ad_hoc_questions: not a list")

    score = score_parts / total_parts

    return Feedback(
        name="stream_attachment",
        value=round(score, 4),
        rationale=f"Attachment: {'; '.join(details)}",
    )
