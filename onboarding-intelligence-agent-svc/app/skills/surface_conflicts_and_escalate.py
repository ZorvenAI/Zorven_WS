"""SKL-OIA-14 — Surface conflicting evidence for a field and escalate for human
resolution.

Design §8.3 · implemented by story J-05.

Builds escalation payloads from detected field conflicts. The PROCESS pipeline
calls ``_handle_conflicts`` directly; this skill provides the standalone
invocation path through the SkillRegistry for LIVE/EDITOR use where the
IG → RBAC → PG → OG chain must run.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.messaging.schemas import ConflictCandidate, EscalationMessage
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult


class SurfaceConflictsAndEscalate(BaseSkill):
    """Surface conflicting evidence for a field and escalate for human resolution."""

    async def run(self, context: SkillContext) -> SkillResult:
        conflicts = context.input_context.get("conflicts", [])

        if not conflicts:
            return SkillResult(
                skill_id=self.meta.skill_id,
                output={
                    "escalation_count": 0,
                    "items": [],
                },
            )

        items: list[dict[str, Any]] = []
        for c in conflicts:
            candidates = _build_candidates(c)
            escalation_id = uuid.uuid4()
            session_id = context.tenant_context.session_id
            msg = EscalationMessage(
                escalation_id=escalation_id,
                tenant_id=uuid.UUID(context.tenant_context.tenant_id),
                session_id=uuid.UUID(session_id) if session_id else None,
                reason_code="FIELD_CONFLICT",
                field_name=c.get("field_name"),
                confidence=c.get("new_confidence"),
                candidates=candidates,
            )
            items.append(
                {
                    "escalation_id": str(msg.escalation_id),
                    "field_name": c.get("field_name"),
                    "reason_code": msg.reason_code,
                    "candidate_count": len(candidates),
                }
            )

        return SkillResult(
            skill_id=self.meta.skill_id,
            output={
                "escalation_count": len(items),
                "severity": "HIGH" if len(items) > 2 else "MEDIUM",
                "items": items,
            },
        )


def _build_candidates(conflict: dict[str, Any]) -> list[ConflictCandidate]:
    """Build ConflictCandidate list from an enriched conflict dict."""
    candidates: list[ConflictCandidate] = []

    existing_span = conflict.get("existing_source_span")
    if existing_span:
        ref = _format_ref(existing_span)
    else:
        ref = f"provenance:{conflict.get('field_name', 'unknown')}"
    candidates.append(
        ConflictCandidate(
            source="existing",
            evidence_ref=ref,
            confidence=conflict.get("existing_confidence"),
        )
    )

    new_evidence = conflict.get("new_evidence", [])
    new_ref = (
        _format_ref(new_evidence[0])
        if new_evidence
        else f"extraction:{conflict.get('field_name', 'unknown')}"
    )
    candidates.append(
        ConflictCandidate(
            source="new",
            evidence_ref=new_ref,
            confidence=conflict.get("new_confidence"),
            classification=conflict.get("new_classification"),
        )
    )

    return candidates


def _format_ref(span: dict[str, Any]) -> str:
    rec_id = span.get("recording_id")
    med_id = span.get("media_id")
    if rec_id:
        t_start = span.get("t_start", "")
        t_end = span.get("t_end", "")
        return f"recording:{rec_id}:{t_start}-{t_end}"
    if med_id:
        return f"media:{med_id}"
    return "unknown"
