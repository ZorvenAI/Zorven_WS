"""J-04 — OG-02 egress redaction and OG-05 tenant isolation.

Chain-compatible rule functions for the OUTPUT layer. Both are registered
at startup in ``app/main.py`` and also called inline during field
extraction (belt-and-braces).
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.logic.guardrails import Action, Verdict
from app.skills.models import SkillContext

logger = get_logger(__name__)

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def og02_egress_redact(payload: Any, context: SkillContext) -> Verdict:
    """OG-02: re-apply PII redaction on output before delivery."""
    from app.skills.redact_pii import redact_text

    if isinstance(payload, str):
        result = redact_text(payload)
        if result.applied:
            logger.info(
                "og02_chain_redaction",
                entity_types=result.entity_types,
            )
            return Verdict(
                rule_id="OG-02",
                action=Action.REDACT,
                detail=f"redacted entity types: {result.entity_types}",
                payload=result.text,
            )
        return Verdict(rule_id="OG-02", action=Action.PASS, payload=payload)

    if isinstance(payload, dict):
        changed = False
        redacted_payload = {}
        for k, v in payload.items():
            if isinstance(v, str):
                result = redact_text(v)
                if result.applied:
                    changed = True
                    redacted_payload[k] = result.text
                else:
                    redacted_payload[k] = v
            else:
                redacted_payload[k] = v

        if changed:
            return Verdict(
                rule_id="OG-02",
                action=Action.REDACT,
                detail="PII redacted from output fields",
                payload=redacted_payload,
            )
        return Verdict(rule_id="OG-02", action=Action.PASS, payload=payload)

    return Verdict(rule_id="OG-02", action=Action.PASS, payload=payload)


def og05_tenant_isolation(payload: Any, context: SkillContext) -> Verdict:
    """OG-05: cross-tenant identifier in output → security BLOCK."""
    own_tenant = context.tenant_context.tenant_id
    if not own_tenant:
        return Verdict(rule_id="OG-05", action=Action.PASS, payload=payload)

    foreign = _scan_for_foreign_tenant(payload, own_tenant)
    if foreign is not None:
        logger.error(
            "og05_chain_cross_tenant_block",
            foreign_tenant_id=foreign,
            detail="cross-tenant identifier in output",
        )
        return Verdict(
            rule_id="OG-05",
            action=Action.BLOCK,
            detail=f"cross-tenant identifier {foreign} found in output",
        )

    return Verdict(rule_id="OG-05", action=Action.PASS, payload=payload)


def _scan_for_foreign_tenant(value: Any, own_tenant_id: str) -> str | None:
    """Recursively scan a value for UUID strings that aren't the own tenant."""
    if isinstance(value, str):
        for match in _UUID_RE.finditer(value):
            found = match.group().lower()
            if found != own_tenant_id.lower():
                return found
    elif isinstance(value, dict):
        for v in value.values():
            result = _scan_for_foreign_tenant(v, own_tenant_id)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in value:
            result = _scan_for_foreign_tenant(item, own_tenant_id)
            if result is not None:
                return result
    return None
