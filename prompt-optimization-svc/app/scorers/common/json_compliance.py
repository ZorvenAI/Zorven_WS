"""JSON compliance scorer (§5.1, AC-1).

Returns 1.0 for valid JSON output, 0.0 on JSONDecodeError with
justification explaining the parse failure.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)


@scorer(name="json_compliance")
def json_compliance(*, inputs, outputs, expectations=None):
    """Score whether the output is valid JSON.

    Args:
        inputs: Model input (unused).
        outputs: Model output text to validate.
        expectations: Expected output (unused).

    Returns:
        Feedback with value 1.0 (valid) or 0.0 (invalid).
    """
    if outputs is None:
        return Feedback(
            name="json_compliance",
            value=0.0,
            rationale="Output is None — cannot parse as JSON.",
        )

    text = str(outputs)

    if not text.strip():
        return Feedback(
            name="json_compliance",
            value=0.0,
            rationale="Output is empty — cannot parse as JSON.",
        )

    try:
        json.loads(text)
        return Feedback(
            name="json_compliance",
            value=1.0,
            rationale="Output is valid JSON.",
        )
    except json.JSONDecodeError as exc:
        return Feedback(
            name="json_compliance",
            value=0.0,
            rationale=f"JSONDecodeError: {exc.msg} (line {exc.lineno}, col {exc.colno}).",
        )
