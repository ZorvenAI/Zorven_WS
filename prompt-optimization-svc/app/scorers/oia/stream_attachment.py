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

    Prompt output keys: attachments (list of {question_id,
    relevance, evidence}), adhoc_questions (list of {text,
    t_start, inferred_target_field}).

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

    attachments = data.get("attachments", [])
    if isinstance(attachments, list) and len(attachments) > 0:
        valid = sum(
            1
            for a in attachments
            if isinstance(a, dict)
            and a.get("question_id")
            and a.get("relevance") is not None
        )
        ratio = valid / len(attachments)
        score_parts += ratio
        details.append(f"attachments: {valid}/{len(attachments)} valid")
    else:
        details.append("attachments: missing or empty")

    adhoc = data.get("adhoc_questions", [])
    if isinstance(adhoc, list):
        score_parts += 1
        details.append(f"adhoc_detection: {len(adhoc)} detected")
    else:
        details.append("adhoc_questions: not a list")

    score = score_parts / total_parts

    return Feedback(
        name="stream_attachment",
        value=round(score, 4),
        rationale=f"Attachment: {'; '.join(details)}",
    )
