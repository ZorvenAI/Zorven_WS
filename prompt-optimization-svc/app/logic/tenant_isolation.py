"""Tenant isolation enforcement for optimization artifacts (§10.3, OPT-10).

Ensures every optimization artifact is scoped to a single tenant or
global namespace. Prevents cross-tenant data leakage in MLflow
experiments, golden datasets, and GEPA reflection traces.
"""

import logging
import re
from typing import Optional, TypeVar

logger = logging.getLogger(__name__)

DEFAULT_EXPERIMENT = "prompt-optimization"
TENANT_EXPERIMENT_TEMPLATE = "prompt-optimization-tenant-{tenant_id}"

# Only allow safe characters in experiment names
_SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9_\-]")

T = TypeVar("T")


def get_mlflow_experiment_name(tenant_id: Optional[str] = None) -> str:
    """Get tenant-scoped MLflow experiment name (AC-1).

    Sanitizes tenant_id to MLflow-safe characters [A-Za-z0-9_-].
    Falls back to global experiment if sanitized ID is empty.

    Args:
        tenant_id: Tenant identifier, or None for global.

    Returns:
        Experiment name: "prompt-optimization" for global,
        "prompt-optimization-tenant-{sanitized_tid}" for tenant-scoped.
    """
    if not tenant_id:
        return DEFAULT_EXPERIMENT
    sanitized = _SAFE_ID_PATTERN.sub("", tenant_id)
    if not sanitized:
        return DEFAULT_EXPERIMENT
    return TENANT_EXPERIMENT_TEMPLATE.format(tenant_id=sanitized)


def filter_golden_examples_by_tenant(
    examples: list[T],
    tenant_id: Optional[str] = None,
) -> list[T]:
    """Filter golden examples by tenant isolation (AC-2).

    Returns examples belonging to the specified tenant plus
    global examples (tenant_id=None). Excludes examples from
    other tenants.

    Args:
        examples: Full list of golden examples.
        tenant_id: Tenant to filter for, or None for global-only.

    Returns:
        Filtered list of examples.
    """
    result: list[T] = []
    for ex in examples:
        ex_tenant = getattr(ex, "tenant_id", None)
        if ex_tenant is None:
            # Global example — always included
            result.append(ex)
        elif tenant_id and ex_tenant == tenant_id:
            # Tenant-specific example matching the requested tenant
            result.append(ex)
        # Other tenant's examples are excluded
    return result


def validate_no_cross_tenant_data(
    reflection_context: str,
    tenant_id: str,
    all_tenant_ids: Optional[list[str]] = None,
) -> bool:
    """Validate GEPA reflection context has no cross-tenant data (AC-3).

    Scans the reflection prompt for tenant_id references that don't
    match the current tenant. Returns False if cross-tenant data
    is detected.

    Args:
        reflection_context: The assembled reflection prompt text.
        tenant_id: The current tenant's identifier.
        all_tenant_ids: Optional list of all known tenant IDs to check.

    Returns:
        True if no cross-tenant data found (safe).
    """
    if not reflection_context or not tenant_id:
        return True

    # Check for explicit tenant_id references in the context
    tenant_pattern = re.compile(
        r"tenant[_\-]?id[\"'\s:=]+([a-zA-Z0-9_\-]+)", re.IGNORECASE
    )

    matches = tenant_pattern.findall(reflection_context)
    for match in matches:
        if match != tenant_id and match.lower() not in ("none", "null", ""):
            logger.warning(
                "Cross-tenant data detected in reflection context: "
                "found tenant '%s' in context for tenant '%s'",
                match,
                tenant_id,
            )
            return False

    # If we have a list of known tenant IDs, use word-boundary regex
    # to avoid false positives (e.g., "t1" matching inside "t10")
    if all_tenant_ids:
        for other_tid in all_tenant_ids:
            if other_tid != tenant_id:
                boundary_pattern = re.compile(r"\b" + re.escape(other_tid) + r"\b")
                if boundary_pattern.search(reflection_context):
                    logger.warning(
                        "Cross-tenant data detected: tenant '%s' found in "
                        "context for tenant '%s'",
                        other_tid,
                        tenant_id,
                    )
                    return False

    return True
