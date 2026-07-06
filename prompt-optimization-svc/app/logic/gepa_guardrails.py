"""GEPA mutation guardrails (OPT-11, OPT-12).

Validates GEPA candidate templates against the original to ensure
placeholder invariance (OPT-11) and schema preamble protection (OPT-12).
"""

import logging

from app.logic.guardrails import GuardrailResult
from app.logic.preamble_validator import (
    PreambleProtectionResult,
    validate_preamble_protection,
)
from app.logic.placeholder_validator import (
    PlaceholderInvarianceResult,
    validate_placeholder_invariance,
)

logger = logging.getLogger(__name__)


def check_gepa_mutation(
    original_template: str,
    candidate_template: str,
) -> tuple[bool, PlaceholderInvarianceResult]:
    """Check whether a GEPA mutation candidate should be accepted.

    A candidate is rejected if it removes any placeholder from the
    original template. New placeholders flag the candidate for
    human review but do not cause rejection.

    Args:
        original_template: The original prompt template.
        candidate_template: The GEPA-generated candidate template.

    Returns:
        Tuple of (accepted, result). accepted=False if placeholders removed.
    """
    result = validate_placeholder_invariance(original_template, candidate_template)

    if not result.valid:
        logger.error(
            "OPT-11: GEPA candidate REJECTED — removed placeholders: %s",
            ", ".join(sorted(result.removed)),
        )
    elif result.needs_review:
        logger.warning(
            "OPT-11: GEPA candidate accepted but FLAGGED FOR REVIEW — "
            "new placeholders: %s",
            ", ".join(sorted(result.added)),
        )

    return result.valid, result


def check_preamble_protection(
    original_template: str,
    candidate_template: str,
    tenant_id: str | None = None,
    prompt_id: str | None = None,
    optimization_run_id: str | None = None,
) -> GuardrailResult:
    """OPT-12: Validate schema preamble hasn't been weakened by GEPA.

    Wraps validate_preamble_protection() into a GuardrailResult.
    Logs detailed violation info for AUDIT trail (AC-2).

    Args:
        original_template: The original prompt template (pre-mutation).
        candidate_template: The GEPA-generated candidate template.
        tenant_id: Tenant identifier for audit logging.
        prompt_id: Prompt identifier for audit logging.
        optimization_run_id: Optimization run ID for audit logging.

    Returns:
        GuardrailResult with passed=False if preamble protection violated.
    """
    result = validate_preamble_protection(original_template, candidate_template)

    if not result.valid:
        logger.error(
            "OPT-12: Schema preamble protection VIOLATION — %s | "
            "tenant_id=%s prompt_id=%s optimization_run_id=%s",
            "; ".join(result.violation_reasons),
            tenant_id,
            prompt_id,
            optimization_run_id,
        )
        return GuardrailResult(
            passed=False,
            guardrail_id="OPT-12",
            message=f"Schema preamble weakened: {'; '.join(result.violation_reasons)}",
            details={
                "preamble_present": result.preamble_present,
                "preamble_at_top": result.preamble_at_top,
                "fields_removed": result.fields_removed,
                "fields_added": result.fields_added,
                "max_length_weakened": result.max_length_weakened,
                "required_relaxed": result.required_relaxed,
                "violation_reasons": result.violation_reasons,
                "tenant_id": tenant_id,
                "prompt_id": prompt_id,
                "optimization_run_id": optimization_run_id,
            },
        )

    return GuardrailResult(
        passed=True,
        guardrail_id="OPT-12",
        message="Schema preamble protection OK",
        details={"preamble_present": result.preamble_present},
    )
