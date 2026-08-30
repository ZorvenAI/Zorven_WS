"""Media analysis accuracy scorer for OIA (§17.1).

Checks OCR text extraction accuracy and usage_tag classification
against admin corrections. Used for both single-frame and multi-frame
media analysis prompts.
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


@scorer(name="media_analysis_accuracy")
def media_analysis_accuracy(*, inputs, outputs, expectations=None):
    """Score media analysis OCR and classification accuracy.

    Checks for: extracted_text (non-empty), usage_tags (list),
    and agreement with expectations when available.

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="media_analysis_accuracy",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    score_parts = 0.0
    total_parts = 3
    details = []

    ocr_text = data.get("extracted_text", data.get("ocr_text", ""))
    if isinstance(ocr_text, str) and len(ocr_text.strip()) > 0:
        score_parts += 1
        details.append(f"extracted_text: {len(ocr_text)} chars")
    else:
        details.append("extracted_text: missing or empty")

    usage_tags = data.get("usage_tags", data.get("tags", []))
    if isinstance(usage_tags, list) and len(usage_tags) > 0:
        score_parts += 1
        details.append(f"usage_tags: {len(usage_tags)} tags")
    else:
        details.append("usage_tags: missing or empty")

    exp_data = _parse_output(expectations) if expectations else None
    if exp_data:
        expected_tags = exp_data.get("expected_tags", [])
        if isinstance(expected_tags, list) and expected_tags:
            predicted = set(
                str(t).lower()
                for t in (usage_tags if isinstance(usage_tags, list) else [])
            )
            expected = set(str(t).lower() for t in expected_tags)
            if expected:
                overlap = len(predicted & expected)
                precision = overlap / len(predicted) if predicted else 0
                recall = overlap / len(expected)
                f1 = (
                    2 * precision * recall / (precision + recall)
                    if (precision + recall) > 0
                    else 0
                )
                score_parts += f1
                details.append(f"tag_f1: {f1:.2f}")
            else:
                score_parts += 1
                details.append("expected_tags: empty reference")
        else:
            score_parts += 0.5
            details.append("no expected_tags for comparison")
    else:
        score_parts += 0.5
        details.append("no expectations provided")

    score = score_parts / total_parts

    return Feedback(
        name="media_analysis_accuracy",
        value=round(score, 4),
        rationale=f"Media accuracy: {'; '.join(details)}",
    )
