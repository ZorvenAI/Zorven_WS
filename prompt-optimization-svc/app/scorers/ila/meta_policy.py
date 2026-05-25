"""Meta policy scorer for ILA (Intelligence Loop Agent).

Evaluates ADPUB output for Meta Ads policy compliance:
plan warnings count, published campaign presence, and sandbox mode flag.
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


@scorer(name="meta_policy")
def meta_policy(*, inputs, outputs, expectations=None):
    """Score Meta Ads policy compliance from ADPUB output.

    Three checks (each worth 1/3):
    1. plan_warnings list has <= 2 entries (fewer is better).
    2. published_campaign dict is present (required for production).
    3. sandbox_mode is a bool (type validation).

    Score = passes / 3.

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="meta_policy",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    passes = 0
    details = []

    # Check 1: plan_warnings <= 2
    plan_warnings = data.get("plan_warnings")
    if isinstance(plan_warnings, list):
        if len(plan_warnings) <= 2:
            passes += 1
            details.append(f"plan_warnings={len(plan_warnings)} (<=2, pass)")
        else:
            details.append(f"plan_warnings={len(plan_warnings)} (>2, fail)")
    else:
        details.append("plan_warnings missing or not a list (fail)")

    # Check 2: published_campaign is a dict
    published_campaign = data.get("published_campaign")
    if isinstance(published_campaign, dict):
        passes += 1
        details.append("published_campaign present (pass)")
    else:
        details.append("published_campaign missing or not a dict (fail)")

    # Check 3: sandbox_mode is a bool
    sandbox_mode = data.get("sandbox_mode")
    if isinstance(sandbox_mode, bool):
        passes += 1
        details.append(f"sandbox_mode={sandbox_mode} is bool (pass)")
    else:
        details.append("sandbox_mode missing or not a bool (fail)")

    score = round(passes / 3, 4)

    return Feedback(
        name="meta_policy",
        value=score,
        rationale=f"{passes}/3 checks passed: {'; '.join(details)}",
    )
