"""Follow-up usefulness scorer for OIA (§17.1).

Stub scorer until G-04 (EVT-105 accepted backfill) lands.
Per AC-2: if a signal doesn't exist yet, register without that scorer
and document the gap. This scorer returns 0.0 with a documented rationale.
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


@scorer(name="followup_usefulness")
def followup_usefulness(*, inputs, outputs, expectations=None):
    """Score follow-up question usefulness via asked-rate proxy.

    STUB: Returns 0.0 until G-04 (EVT-105 accepted backfill) provides
    the asked-rate signal. The scorer structure is complete so GEPA
    can wire it without code changes once the signal exists.

    Returns:
        Feedback with value 0.0 and gap documentation.
    """
    return Feedback(
        name="followup_usefulness",
        value=0.0,
        rationale=(
            "Signal source EVT-105 accepted backfill not yet available "
            "(G-04). Scorer registered as stub per AC-2."
        ),
    )
