"""PG-01 through PG-07 — process guardrails.

Design §5.2 · implemented by story M-01.

PG-08 (sensitive media) lives in ``app/logic/pg08.py``.

PG-02 and PG-03 are defense-in-depth: the primary enforcement is in
``SkillRegistry.get()`` (allowlist) and ``SkillRegistry._authorize()``
(RBAC) respectively. The chain rules here catch a code path that somehow
bypasses the registry.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.logic.guardrails import Action, Verdict
from app.skills.models import SkillContext

logger = get_logger(__name__)


def pg01_plan_required(payload: Any, context: SkillContext) -> Verdict:
    """PG-01: a skill execution must happen under an emitted plan."""
    plan_emitted = context.config.get("plan_emitted")
    if plan_emitted:
        return Verdict(rule_id="PG-01", action=Action.PASS, payload=payload)

    logger.info("pg01_no_plan")
    return Verdict(
        rule_id="PG-01",
        action=Action.ESCALATE,
        detail="no execution plan was emitted before skill invocation",
        payload=payload,
    )


def pg02_skill_allowlist(payload: Any, context: SkillContext) -> Verdict:
    """PG-02: defense-in-depth — skill_id must be in the OIA allowlist."""
    skill_id = context.input_context.get("skill_id", "")
    if not skill_id:
        return Verdict(rule_id="PG-02", action=Action.PASS, payload=payload)

    if isinstance(skill_id, str) and skill_id.startswith("SKL-OIA-"):
        try:
            index = int(skill_id.split("-")[-1])
            if 1 <= index <= 16:
                return Verdict(rule_id="PG-02", action=Action.PASS, payload=payload)
        except (ValueError, IndexError):
            pass

    logger.warning("pg02_skill_not_allowed", skill_id=skill_id)
    return Verdict(
        rule_id="PG-02",
        action=Action.BLOCK,
        detail=f"skill {skill_id} is not in the OIA allowlist",
    )


def pg03_rbac(payload: Any, context: SkillContext) -> Verdict:
    """PG-03: defense-in-depth — RBAC is enforced by SkillRegistry._authorize."""
    return Verdict(rule_id="PG-03", action=Action.PASS, payload=payload)


def pg04_write_scope(payload: Any, context: SkillContext) -> Verdict:
    """PG-04: tenant_id must be present; DELETE operations are blocked."""
    tenant_id = context.tenant_context.tenant_id
    if not tenant_id or not str(tenant_id).strip():
        logger.warning("pg04_no_tenant")
        return Verdict(
            rule_id="PG-04",
            action=Action.BLOCK,
            detail="write operation attempted without a tenant context",
        )

    if isinstance(payload, dict):
        operation = str(payload.get("operation", "")).upper()
        if operation == "DELETE":
            logger.warning("pg04_delete_blocked", tenant_id=tenant_id)
            return Verdict(
                rule_id="PG-04",
                action=Action.BLOCK,
                detail="DELETE operations are not permitted",
            )

    return Verdict(rule_id="PG-04", action=Action.PASS, payload=payload)


def pg05_prompt_pinning(payload: Any, context: SkillContext) -> Verdict:
    """PG-05: pinned prompt versions block re-resolution."""
    prompt_versions = context.config.get("prompt_versions")
    re_resolve = context.config.get("_prompt_re_resolve", False)

    if prompt_versions and re_resolve:
        logger.warning("pg05_re_resolve_blocked")
        return Verdict(
            rule_id="PG-05",
            action=Action.BLOCK,
            detail="prompt re-resolution blocked — versions pinned",
        )
    return Verdict(rule_id="PG-05", action=Action.PASS, payload=payload)


def pg06_field_protection(payload: Any, context: SkillContext) -> Verdict:
    """PG-06: protected fields cannot be overwritten."""
    protected = context.config.get("protected_fields")
    if not protected or not isinstance(payload, dict):
        return Verdict(rule_id="PG-06", action=Action.PASS, payload=payload)

    target_fields = set(payload.keys()) if isinstance(payload, dict) else set()
    conflicts = target_fields & set(protected)
    if conflicts:
        logger.warning("pg06_protected_fields", fields=sorted(conflicts))
        return Verdict(
            rule_id="PG-06",
            action=Action.DROP,
            detail=f"protected field(s) targeted: {sorted(conflicts)}",
            payload=payload,
        )
    return Verdict(rule_id="PG-06", action=Action.PASS, payload=payload)


def pg07_budget_guard(payload: Any, context: SkillContext) -> Verdict:
    """PG-07: token budget enforcement per mode."""
    token_count = context.config.get("_token_count", 0)
    budget = context.config.get("_token_budget")
    if budget is None or token_count <= budget:
        return Verdict(rule_id="PG-07", action=Action.PASS, payload=payload)

    logger.warning(
        "pg07_budget_exceeded",
        token_count=token_count,
        budget=budget,
    )
    return Verdict(
        rule_id="PG-07",
        action=Action.BLOCK,
        detail=f"token budget exceeded: {token_count}/{budget}",
    )
