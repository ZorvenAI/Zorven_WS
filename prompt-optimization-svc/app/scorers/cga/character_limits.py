"""Character limits scorer for CGA (§5.2.1, AC-2).

Enforces Meta Ads character limits: 40 (headline/hook), 125 (primary text), 30 (CTA).
Zero-tolerance rule: any field >10 chars over limit triggers immediate 0.0.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

# Meta Ads character limits
HOOK_LIMIT = 40
COPY_LIMITS = {"short": 125, "medium": 200, "long": 500}
CTA_LIMIT = 30

# Zero-tolerance overflow threshold
OVERFLOW_TOLERANCE = 10


def _parse_cga_output(outputs) -> dict | None:
    """Parse CGA output from JSON string or dict."""
    if outputs is None:
        return None
    if isinstance(outputs, dict):
        return outputs
    try:
        parsed = json.loads(str(outputs))
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


@scorer(name="character_limits")
def character_limits(*, inputs, outputs, expectations=None):
    """Score adherence to Meta Ads character limits.

    Args:
        inputs: Model input (unused).
        outputs: CGA response JSON with hooks, copy_variants, ctas.
        expectations: Optional (unused).

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_cga_output(outputs)
    if data is None:
        return Feedback(
            name="character_limits",
            value=0.0,
            rationale="Invalid or missing CGA output.",
        )

    violations = []
    total = 0
    compliant = 0

    # Check hooks (≤40 chars)
    hooks = data.get("hooks", [])
    if isinstance(hooks, list):
        for hook in hooks:
            if not isinstance(hook, dict):
                continue
            total += 1
            text = hook.get("hook_text", "")
            char_count = len(text)
            if char_count > HOOK_LIMIT + OVERFLOW_TOLERANCE:
                return Feedback(
                    name="character_limits",
                    value=0.0,
                    rationale=f"Zero-tolerance violation: hook has {char_count} chars (limit {HOOK_LIMIT}, >{OVERFLOW_TOLERANCE} over).",
                )
            elif char_count > HOOK_LIMIT:
                violations.append(f"hook ({char_count}/{HOOK_LIMIT})")
            else:
                compliant += 1

    # Check copy variants (short ≤125, medium ≤200, long ≤500)
    copy_variants = data.get("copy_variants", [])
    if isinstance(copy_variants, list):
        for cv in copy_variants:
            if not isinstance(cv, dict):
                continue
            total += 1
            text = cv.get("copy_text", "")
            char_count = len(text)
            label = cv.get("length_label", "short")
            limit = COPY_LIMITS.get(label, COPY_LIMITS["short"])

            if char_count > limit + OVERFLOW_TOLERANCE:
                return Feedback(
                    name="character_limits",
                    value=0.0,
                    rationale=f"Zero-tolerance violation: {label} copy has {char_count} chars (limit {limit}, >{OVERFLOW_TOLERANCE} over).",
                )
            elif char_count > limit:
                violations.append(f"{label} copy ({char_count}/{limit})")
            else:
                compliant += 1

    # Check CTAs (≤30 chars)
    ctas = data.get("ctas", [])
    if isinstance(ctas, list):
        for cta in ctas:
            if not isinstance(cta, dict):
                continue
            total += 1
            text = cta.get("cta_text", "")
            char_count = len(text)
            if char_count > CTA_LIMIT + OVERFLOW_TOLERANCE:
                return Feedback(
                    name="character_limits",
                    value=0.0,
                    rationale=f"Zero-tolerance violation: CTA has {char_count} chars (limit {CTA_LIMIT}, >{OVERFLOW_TOLERANCE} over).",
                )
            elif char_count > CTA_LIMIT:
                violations.append(f"CTA ({char_count}/{CTA_LIMIT})")
            else:
                compliant += 1

    if total == 0:
        return Feedback(
            name="character_limits",
            value=0.0,
            rationale="No hooks, copy variants, or CTAs found in output.",
        )

    score = round(compliant / total, 4)

    rationale = f"{compliant}/{total} items within character limits."
    if violations:
        rationale += f" Violations: {', '.join(violations[:5])}"

    return Feedback(
        name="character_limits",
        value=score,
        rationale=rationale,
    )
