"""Guardrail compliance scorer for COA (§5.2.3, AC-1).

Returns 0.0 when any PG-01..PG-10 or OG guardrail is violated.
Zero-tolerance: a single failure means the entire output fails.
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


@scorer(name="guardrail_compliance")
def guardrail_compliance(*, inputs, outputs, expectations=None):
    """Score guardrail compliance with zero tolerance.

    If any guardrail result has passed=False, score is 0.0.
    All guardrails must pass for a score of 1.0.

    Returns:
        Feedback with value 0.0 or 1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="guardrail_compliance",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    report = data.get("guardrail_report")
    if not isinstance(report, dict):
        return Feedback(
            name="guardrail_compliance",
            value=0.0,
            rationale="Missing or invalid 'guardrail_report' field.",
        )

    results = report.get("results")
    if not isinstance(results, list):
        return Feedback(
            name="guardrail_compliance",
            value=0.0,
            rationale="No guardrail results found.",
        )

    if not results:
        return Feedback(
            name="guardrail_compliance",
            value=0.0,
            rationale="Empty guardrail results.",
        )

    # Filter to PG and OG rules only (AC-1: PG-01..PG-10, OG)
    pg_og_results = []
    for r in results:
        if not isinstance(r, dict):
            continue
        rule_id = r.get("rule_id", "")
        if rule_id.startswith("PG-") or rule_id.startswith("OG"):
            pg_og_results.append(r)

    if not pg_og_results:
        return Feedback(
            name="guardrail_compliance",
            value=0.0,
            rationale="No PG/OG guardrail results found.",
        )

    failed_rules = []
    for r in pg_og_results:
        if not r.get("passed", True):
            rule_id = r.get("rule_id", "unknown")
            message = r.get("message", "")
            failed_rules.append(f"{rule_id}: {message}")

    if failed_rules:
        return Feedback(
            name="guardrail_compliance",
            value=0.0,
            rationale=f"Guardrail violations: {'; '.join(failed_rules[:5])}"
            + (f" (+{len(failed_rules) - 5} more)" if len(failed_rules) > 5 else ""),
        )

    return Feedback(
        name="guardrail_compliance",
        value=1.0,
        rationale=f"All {len(pg_og_results)} PG/OG guardrail checks passed.",
    )
