"""GEPA mutation guardrails (OPT-11).

Validates GEPA candidate templates against the original to ensure
placeholder invariance and template-context separation.
"""

import logging

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
