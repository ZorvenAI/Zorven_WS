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

    Checks for: key_moments (with timestamps), summary_text (non-empty),
    and speaker attribution.

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

    summary_text = data.get("summary", data.get("summary_text", ""))
    if isinstance(summary_text, str) and len(summary_text.strip()) > 0:
        score_parts += 1
        details.append(f"summary: {len(summary_text)} chars")
    else:
        details.append("summary: missing or empty")

    key_moments = data.get("key_moments", data.get("moments", []))
    if isinstance(key_moments, list) and len(key_moments) > 0:
        timestamped = sum(
            1
            for m in key_moments
            if isinstance(m, dict)
            and (m.get("timestamp") is not None or m.get("t_start") is not None)
        )
        ratio = timestamped / len(key_moments) if key_moments else 0
        score_parts += ratio
        details.append(f"key_moments: " f"{timestamped}/{len(key_moments)} timestamped")
    else:
        details.append("key_moments: missing or empty")

    speakers = data.get("speakers", data.get("speaker_segments", []))
    if isinstance(speakers, list) and len(speakers) > 0:
        score_parts += 1
        details.append(f"speakers: {len(speakers)} identified")
    elif isinstance(summary_text, str) and "speaker" in summary_text.lower():
        score_parts += 0.5
        details.append("speakers: referenced in summary text")
    else:
        details.append("speakers: not attributed")

    score = score_parts / total_parts

    return Feedback(
        name="summary_faithfulness",
        value=round(score, 4),
        rationale=f"Faithfulness: {'; '.join(details)}",
    )
