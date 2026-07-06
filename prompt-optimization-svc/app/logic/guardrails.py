"""Unified optimization guardrails OPT-01 through OPT-10 (§18.1, US-049).

Standardized GuardrailResult dataclass and individual check functions
for dataset size (OPT-01), cost cap (OPT-02), length sanity (OPT-06),
distributed lock (OPT-07), prompt injection scan (OPT-09), and tenant
isolation (OPT-10). Two-phase orchestrator: pre-optimization and
per-candidate checks.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.cache.prompt_cache import PromptCacheManager
from app.cache.tenant_config import MIN_DATASET_SIZE
from app.core.config import settings
from app.datasets.sampler import InsufficientDatasetError, validate_dataset_size
from app.logic.tenant_isolation import validate_no_cross_tenant_data

logger = logging.getLogger(__name__)


@dataclass
class GuardrailResult:
    """Result of a single guardrail check."""

    passed: bool
    guardrail_id: str
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class GuardrailChainResult:
    """Result of running a chain of guardrail checks."""

    all_passed: bool
    results: list[GuardrailResult]
    first_failure: Optional[GuardrailResult]


# ── OPT-09: Prompt injection patterns ──

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?prior\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+are\s+", re.IGNORECASE),
    re.compile(r"^system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"```\s*system", re.IGNORECASE),
    re.compile(r"override\s+safety", re.IGNORECASE),
    re.compile(r"bypass\s+(all\s+)?restrictions", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your)\s+(you|above|previous)", re.IGNORECASE),
]


# ── Individual guardrail functions ──


def check_dataset_size(examples: list, min_size: int) -> GuardrailResult:
    """OPT-01: Validate dataset meets minimum size with hard floor of 3.

    Args:
        examples: List of golden examples.
        min_size: Requested minimum size (will be clamped to hard floor).

    Returns:
        GuardrailResult with passed=True if dataset is large enough.
    """
    effective_min = max(MIN_DATASET_SIZE, min_size)
    try:
        validate_dataset_size(examples, effective_min)
    except InsufficientDatasetError:
        return GuardrailResult(
            passed=False,
            guardrail_id="OPT-01",
            message=(
                f"Insufficient dataset: {len(examples)} examples, "
                f"minimum {effective_min} required"
            ),
            details={"actual": len(examples), "minimum": effective_min},
        )
    return GuardrailResult(
        passed=True,
        guardrail_id="OPT-01",
        message="Dataset size OK",
        details={"actual": len(examples), "minimum": effective_min},
    )


def check_cost_cap(
    current_cost_usd: float,
    cap_usd: Optional[float] = None,
) -> GuardrailResult:
    """OPT-02: Check if optimization cost has reached the cap.

    Returns passed=False for graceful stop (not an exception).

    Args:
        current_cost_usd: Accumulated cost so far.
        cap_usd: Cost cap in USD. Defaults to settings.OPTIMIZATION_COST_CAP_USD.
    """
    if cap_usd is None:
        cap_usd = settings.OPTIMIZATION_COST_CAP_USD
    utilization = (current_cost_usd / cap_usd * 100) if cap_usd > 0 else 0.0
    if current_cost_usd >= cap_usd:
        return GuardrailResult(
            passed=False,
            guardrail_id="OPT-02",
            message=f"Cost cap reached: ${current_cost_usd:.2f} >= ${cap_usd:.2f}",
            details={
                "current_cost_usd": current_cost_usd,
                "cap_usd": cap_usd,
                "utilization_pct": round(utilization, 1),
            },
        )
    return GuardrailResult(
        passed=True,
        guardrail_id="OPT-02",
        message=f"Cost within cap: ${current_cost_usd:.2f} / ${cap_usd:.2f}",
        details={
            "current_cost_usd": current_cost_usd,
            "cap_usd": cap_usd,
            "utilization_pct": round(utilization, 1),
        },
    )


def check_length_sanity(
    candidate_text: str,
    base_text: str,
    multiplier_limit: Optional[float] = None,
) -> GuardrailResult:
    """OPT-06: Flag candidates exceeding 3x base prompt length.

    Args:
        candidate_text: The GEPA candidate prompt.
        base_text: The current production prompt.
        multiplier_limit: Max allowed length ratio. Defaults to settings.LENGTH_MULTIPLIER_LIMIT.
    """
    if multiplier_limit is None:
        multiplier_limit = settings.LENGTH_MULTIPLIER_LIMIT
    base_len = max(1, len(base_text))
    candidate_len = len(candidate_text)
    ratio = candidate_len / base_len
    if ratio > multiplier_limit:
        return GuardrailResult(
            passed=False,
            guardrail_id="OPT-06",
            message=(
                f"Candidate too long: {candidate_len} chars is "
                f"{ratio:.1f}x base length ({base_len} chars), "
                f"limit is {multiplier_limit}x"
            ),
            details={
                "candidate_length": candidate_len,
                "base_length": base_len,
                "ratio": round(ratio, 2),
                "limit": multiplier_limit,
            },
        )
    return GuardrailResult(
        passed=True,
        guardrail_id="OPT-06",
        message="Length within limits",
        details={
            "candidate_length": candidate_len,
            "base_length": base_len,
            "ratio": round(ratio, 2),
            "limit": multiplier_limit,
        },
    )


async def check_distributed_lock(
    cache_manager: PromptCacheManager,
    group: str,
    owner: str,
) -> GuardrailResult:
    """OPT-07: Acquire distributed lock for optimization group.

    The caller MUST release the lock via cache_manager.release_optimization_lock()
    in a finally block after the optimization run completes.

    Args:
        cache_manager: PromptCacheManager with lock methods.
        group: Optimization group name.
        owner: Lock owner identifier (e.g., run_id).
    """
    acquired = await cache_manager.acquire_optimization_lock(group, owner)
    if acquired:
        return GuardrailResult(
            passed=True,
            guardrail_id="OPT-07",
            message=f"Lock acquired for group '{group}'",
            details={"group": group, "owner": owner},
        )
    lock_info = await cache_manager.get_optimization_lock_info(group)
    current_owner = lock_info.get("owner", "unknown") if lock_info else "unknown"
    ttl = lock_info.get("ttl_seconds", -1) if lock_info else -1
    return GuardrailResult(
        passed=False,
        guardrail_id="OPT-07",
        message=f"Optimization group '{group}' is already locked",
        details={
            "group": group,
            "requested_owner": owner,
            "current_owner": current_owner,
            "ttl_seconds": ttl,
        },
    )


def check_prompt_injection(candidate_text: str) -> GuardrailResult:
    """OPT-09: Scan candidate for role-hijack injection patterns.

    Blocks candidates containing patterns like "ignore previous instructions",
    "you are now", system tag injection, etc.

    Args:
        candidate_text: The GEPA candidate prompt text.
    """
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(candidate_text)
        if match:
            logger.warning(
                "OPT-09: Injection pattern detected: '%s'",
                match.group(),
            )
            return GuardrailResult(
                passed=False,
                guardrail_id="OPT-09",
                message=f"Prompt injection detected: '{match.group()}'",
                details={
                    "matched_pattern": pattern.pattern,
                    "match_text": match.group(),
                },
            )
    return GuardrailResult(
        passed=True,
        guardrail_id="OPT-09",
        message="No injection patterns detected",
    )


def check_tenant_isolation(
    reflection_context: str,
    tenant_id: str,
    all_tenant_ids: Optional[list[str]] = None,
) -> GuardrailResult:
    """OPT-10: Validate no cross-tenant data in reflection traces.

    Wraps existing validate_no_cross_tenant_data() into GuardrailResult.

    Args:
        reflection_context: The assembled reflection prompt text.
        tenant_id: The current tenant's identifier.
        all_tenant_ids: Optional list of all known tenant IDs.
    """
    safe = validate_no_cross_tenant_data(reflection_context, tenant_id, all_tenant_ids)
    if safe:
        return GuardrailResult(
            passed=True,
            guardrail_id="OPT-10",
            message="No cross-tenant data detected",
            details={"tenant_id": tenant_id},
        )
    return GuardrailResult(
        passed=False,
        guardrail_id="OPT-10",
        message=f"Cross-tenant data detected in reflection context for tenant '{tenant_id}'",
        details={"tenant_id": tenant_id},
    )


# ── Orchestrator functions ──


def _build_chain_result(results: list[GuardrailResult]) -> GuardrailChainResult:
    """Build a GuardrailChainResult from a list of individual results."""
    failures = [r for r in results if not r.passed]
    return GuardrailChainResult(
        all_passed=len(failures) == 0,
        results=results,
        first_failure=failures[0] if failures else None,
    )


async def run_pre_optimization_guardrails(
    examples: list,
    min_dataset_size: int,
    cache_manager: PromptCacheManager,
    optimization_group: str,
    lock_owner: str,
) -> GuardrailChainResult:
    """Run OPT-01 and OPT-07 before optimization starts.

    Short-circuits on first failure.
    """
    results: list[GuardrailResult] = []

    # OPT-01: Dataset size
    r = check_dataset_size(examples, min_dataset_size)
    results.append(r)
    if not r.passed:
        return _build_chain_result(results)

    # OPT-07: Distributed lock
    r = await check_distributed_lock(cache_manager, optimization_group, lock_owner)
    results.append(r)

    return _build_chain_result(results)


def run_candidate_guardrails(
    candidate_text: str,
    base_text: str,
    current_cost_usd: float,
    tenant_id: Optional[str] = None,
    reflection_context: Optional[str] = None,
    all_tenant_ids: Optional[list[str]] = None,
    prompt_id: Optional[str] = None,
    optimization_run_id: Optional[str] = None,
) -> GuardrailChainResult:
    """Run OPT-02, OPT-06, OPT-09, OPT-10, OPT-12 on a candidate.

    Short-circuits on first failure.
    """
    from app.logic.gepa_guardrails import check_preamble_protection

    results: list[GuardrailResult] = []

    # OPT-02: Cost cap
    r = check_cost_cap(current_cost_usd)
    results.append(r)
    if not r.passed:
        return _build_chain_result(results)

    # OPT-06: Length sanity
    r = check_length_sanity(candidate_text, base_text)
    results.append(r)
    if not r.passed:
        return _build_chain_result(results)

    # OPT-09: Injection scan
    r = check_prompt_injection(candidate_text)
    results.append(r)
    if not r.passed:
        return _build_chain_result(results)

    # OPT-10: Tenant isolation (only if tenant context provided)
    if tenant_id and reflection_context is not None:
        r = check_tenant_isolation(reflection_context, tenant_id, all_tenant_ids)
        results.append(r)
        if not r.passed:
            return _build_chain_result(results)

    # OPT-12: Schema preamble protection
    r = check_preamble_protection(
        base_text,
        candidate_text,
        tenant_id=tenant_id,
        prompt_id=prompt_id,
        optimization_run_id=optimization_run_id,
    )
    results.append(r)
    if not r.passed:
        return _build_chain_result(results)

    return _build_chain_result(results)
