"""Creative compliance scorer for CGA (§5.2.1, AC-1).

Enforces JSON validity and presence of required CGA fields.
Scores based on ratio of passing compliance results.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"hooks", "copy_variants", "ctas", "compliance_results"}


def _parse_cga_output(outputs) -> dict | None:
    """Parse CGA output from JSON string or dict."""
    if outputs is None:
        return None
    if isinstance(outputs, dict):
        return outputs
    try:
        parsed = json.loads(str(outputs))
        if isinstance(parsed, dict):
            return parsed
        return None
    except (json.JSONDecodeError, ValueError):
        return None


@scorer(name="creative_compliance")
def creative_compliance(*, inputs, outputs, expectations=None):
    """Score CGA output for Meta Ads compliance.

    Validates JSON structure and scores the ratio of passing
    compliance results to total results.

    Args:
        inputs: Model input (unused).
        outputs: CGA response JSON with compliance_results.
        expectations: Optional (unused).

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_cga_output(outputs)
    if data is None:
        return Feedback(
            name="creative_compliance",
            value=0.0,
            rationale="Invalid or missing CGA output — cannot parse as JSON.",
        )

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        return Feedback(
            name="creative_compliance",
            value=0.0,
            rationale=f"Missing required fields: {', '.join(sorted(missing))}.",
        )

    results = data.get("compliance_results", [])
    if not isinstance(results, list):
        return Feedback(
            name="creative_compliance",
            value=0.0,
            rationale="compliance_results is not a list.",
        )
    # Filter to valid dict entries only
    results = [r for r in results if isinstance(r, dict)]
    if not results:
        return Feedback(
            name="creative_compliance",
            value=0.0,
            rationale="No compliance results found in output.",
        )

    total = len(results)
    pass_count = sum(1 for r in results if r.get("status") == "pass")
    warning_count = sum(1 for r in results if r.get("status") == "warning")
    fail_count = total - pass_count - warning_count

    # Warnings count as half credit
    score = round((pass_count + warning_count * 0.5) / total, 4)

    violations = []
    for r in results:
        if r.get("status") != "pass":
            vid = r.get("variant_id", "unknown")
            vtype = r.get("variant_type", "unknown")
            status = r.get("status", "unknown")
            violations.append(f"{vtype}:{vid}={status}")

    rationale = (
        f"{pass_count} pass, {warning_count} warning, {fail_count} fail "
        f"out of {total} checks."
    )
    if violations:
        rationale += f" Violations: {', '.join(violations[:5])}"
        if len(violations) > 5:
            rationale += f" (+{len(violations) - 5} more)"

    return Feedback(
        name="creative_compliance",
        value=score,
        rationale=rationale,
    )
