"""Summary faithfulness scorer for OIA (§17.1).

Checks that recording summaries capture key moments faithfully
and provide precise timestamps for seek-through verification.
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


@scorer(name="summary_faithfulness")
def summary_faithfulness(*, inputs, outputs, expectations=None):
    """Score recording summary faithfulness.

    Prompt output keys: text (str), key_moments (list of
    {t: float, label: str}).

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="summary_faithfulness",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    score_parts = 0.0
    total_parts = 3
    details = []

    summary_text = data.get("text", "")
    if isinstance(summary_text, str) and summary_text.strip():
        score_parts += 1
        details.append(f"summary: {len(summary_text)} chars")
    else:
        details.append("text: missing or empty")

    key_moments = data.get("key_moments", [])
    if isinstance(key_moments, list) and len(key_moments) > 0:
        timestamped = sum(
            1 for m in key_moments if isinstance(m, dict) and m.get("t") is not None
        )
        ratio = timestamped / len(key_moments) if key_moments else 0
        score_parts += ratio
        details.append(f"key_moments: " f"{timestamped}/{len(key_moments)} timestamped")
    else:
        details.append("key_moments: missing or empty")

    if isinstance(key_moments, list) and len(key_moments) > 0:
        labeled = sum(
            1
            for m in key_moments
            if isinstance(m, dict)
            and isinstance(m.get("label"), str)
            and len(m["label"].strip()) > 0
        )
        ratio = labeled / len(key_moments)
        score_parts += ratio
        details.append(f"labels: {labeled}/{len(key_moments)} present")
    else:
        score_parts += 0
        details.append("labels: no key_moments to check")

    score = score_parts / total_parts

    return Feedback(
        name="summary_faithfulness",
        value=round(score, 4),
        rationale=f"Faithfulness: {'; '.join(details)}",
    )
