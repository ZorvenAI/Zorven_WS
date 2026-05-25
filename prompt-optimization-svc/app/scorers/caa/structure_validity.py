"""Structure validity scorer for CAA (§5.2.2, AC-1).

Validates campaign → ad set → ad hierarchy in JSON output.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

BLUEPRINT_REQUIRED = ("campaign_name", "campaign_objective")
AD_SET_REQUIRED = ("name", "funnel_stage", "targeting")


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


@scorer(name="structure_validity")
def structure_validity(*, inputs, outputs, expectations=None):
    """Score campaign blueprint structural validity.

    Validates the campaign → ad set hierarchy: blueprint must contain
    campaign_name, campaign_objective, and a non-empty ad_sets list
    where each ad set has name, funnel_stage, and targeting.

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="structure_validity",
            value=0.0,
            rationale="Invalid or missing output — cannot parse as JSON.",
        )

    blueprint = data.get("blueprint")
    if not isinstance(blueprint, dict):
        return Feedback(
            name="structure_validity",
            value=0.0,
            rationale="Missing or invalid 'blueprint' field.",
        )

    # Check blueprint-level required fields (presence, not truthiness)
    checks_passed = 0
    checks_total = 0
    issues = []

    for field in BLUEPRINT_REQUIRED:
        checks_total += 1
        if field in blueprint:
            checks_passed += 1
        else:
            issues.append(f"blueprint.{field} missing")

    # Validate ad_sets — check presence, type, and non-empty separately
    checks_total += 1  # presence check
    ad_sets = blueprint.get("ad_sets")
    if ad_sets is not None:
        checks_passed += 1
    else:
        issues.append("blueprint.ad_sets missing")

    if not isinstance(ad_sets, list):
        checks_total += 1
        issues.append("ad_sets is not a list")
        score = round(checks_passed / max(checks_total, 1), 4)
        return Feedback(
            name="structure_validity",
            value=score,
            rationale=f"{checks_passed}/{checks_total} checks passed. Issues: {', '.join(issues)}",
        )

    checks_total += 1  # non-empty check
    if not ad_sets:
        issues.append("ad_sets is empty")
        score = round(checks_passed / max(checks_total, 1), 4)
        return Feedback(
            name="structure_validity",
            value=score,
            rationale=f"{checks_passed}/{checks_total} checks passed. Issues: {', '.join(issues)}",
        )

    checks_passed += 1  # ad_sets is non-empty

    # Validate each ad set
    for i, ad_set in enumerate(ad_sets):
        if not isinstance(ad_set, dict):
            checks_total += 1
            issues.append(f"ad_sets[{i}] is not a dict")
            continue
        for field in AD_SET_REQUIRED:
            checks_total += 1
            if field in ad_set and ad_set[field]:
                checks_passed += 1
            else:
                issues.append(f"ad_sets[{i}].{field} missing")

    score = round(checks_passed / max(checks_total, 1), 4)

    rationale = f"{checks_passed}/{checks_total} structural checks passed."
    if issues:
        rationale += f" Issues: {', '.join(issues[:5])}"
        if len(issues) > 5:
            rationale += f" (+{len(issues) - 5} more)"

    return Feedback(
        name="structure_validity",
        value=score,
        rationale=rationale,
    )
