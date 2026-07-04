"""Human approval gate for CRITICAL agents (§11.2, OPT-05).

ADPUB and COA prompts cannot auto-promote — they require explicit
OWNER/ADMIN approval through the approve/reject API.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.logic.run_lifecycle import RunLifecycleManager, RunState

logger = logging.getLogger(__name__)

# Agents that touch ad spend — auto-promotion permanently disabled (AC-1)
CRITICAL_AGENTS = ("adpub", "coa")


def requires_approval(agent_code: str) -> bool:
    """Check if an agent requires human approval for promotion.

    Returns True for CRITICAL agents (ADPUB, COA) regardless of
    improvement score. Auto-promotion is permanently disabled.

    Args:
        agent_code: Agent code (case-insensitive).

    Returns:
        True if human approval is required.
    """
    if not agent_code:
        return False
    return agent_code.lower() in CRITICAL_AGENTS


@dataclass
class ApprovalDecision:
    """Record of an approval or rejection decision."""

    run_id: str
    agent_code: str
    prompt_name: str
    decision: str  # "approved" | "rejected"
    approved_by: str
    reason: str = ""
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


async def approve_run(
    run_id: str,
    approved_by: str,
    lifecycle_manager: RunLifecycleManager,
    producer=None,
    prompt_name: str = "",
    agent_code: str = "",
) -> ApprovalDecision:
    """Approve a PENDING_APPROVAL run for canary deployment.

    Transitions PENDING_APPROVAL → CANARY and emits audit event (AC-3).

    Args:
        run_id: Optimization run ID.
        approved_by: User/role who approved.
        lifecycle_manager: Run lifecycle manager.
        producer: Kafka lifecycle producer (optional).
        prompt_name: Prompt name for audit.
        agent_code: Agent code for audit.

    Returns:
        ApprovalDecision with decision="approved".
    """
    await lifecycle_manager.transition(
        run_id=run_id,
        from_state=RunState.PENDING_APPROVAL,
        to_state=RunState.CANARY,
        prompt_name=prompt_name,
        agent_code=agent_code,
    )

    # Emit audit event (AC-3)
    if producer is not None:
        producer.send_lifecycle_event_sync(
            event_type="optimization.run.approved",
            prompt_name=prompt_name,
            version=0,
            from_state=RunState.PENDING_APPROVAL.value,
            to_state=RunState.CANARY.value,
        )

    decision = ApprovalDecision(
        run_id=run_id,
        agent_code=agent_code,
        prompt_name=prompt_name,
        decision="approved",
        approved_by=approved_by,
    )

    logger.info(
        "Run %s APPROVED by %s: %s (%s) → CANARY",
        run_id,
        approved_by,
        prompt_name,
        agent_code,
    )
    return decision


async def reject_run(
    run_id: str,
    approved_by: str,
    reason: str,
    lifecycle_manager: RunLifecycleManager,
    producer=None,
    prompt_name: str = "",
    agent_code: str = "",
) -> ApprovalDecision:
    """Reject a PENDING_APPROVAL run.

    Transitions PENDING_APPROVAL → REJECTED and emits audit event (AC-3).

    Args:
        run_id: Optimization run ID.
        approved_by: User/role who rejected.
        reason: Rejection reason.
        lifecycle_manager: Run lifecycle manager.
        producer: Kafka lifecycle producer (optional).
        prompt_name: Prompt name for audit.
        agent_code: Agent code for audit.

    Returns:
        ApprovalDecision with decision="rejected".
    """
    await lifecycle_manager.transition(
        run_id=run_id,
        from_state=RunState.PENDING_APPROVAL,
        to_state=RunState.REJECTED,
        prompt_name=prompt_name,
        agent_code=agent_code,
        error_message=f"Rejected by {approved_by}: {reason}",
    )

    # Emit audit event (AC-3)
    if producer is not None:
        producer.send_lifecycle_event_sync(
            event_type="optimization.run.approval_rejected",
            prompt_name=prompt_name,
            version=0,
            from_state=RunState.PENDING_APPROVAL.value,
            to_state=RunState.REJECTED.value,
        )

    decision = ApprovalDecision(
        run_id=run_id,
        agent_code=agent_code,
        prompt_name=prompt_name,
        decision="rejected",
        approved_by=approved_by,
        reason=reason,
    )

    logger.warning(
        "Run %s REJECTED by %s: %s (%s) — reason: %s",
        run_id,
        approved_by,
        prompt_name,
        agent_code,
        reason,
    )
    return decision
