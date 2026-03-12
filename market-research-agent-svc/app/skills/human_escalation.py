"""SKL-MRA-08: Human Escalation — Emit escalation events via Kafka."""

import logging
import time
import uuid

from app.messaging.kafka_producer import AuditProducer
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class HumanEscalation(BaseSkill):
    """Emits escalation events when human review is needed."""

    meta = SkillMeta(
        skill_id="SKL-MRA-08",
        name="human_escalation",
        description="Escalate to human review via Kafka event",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        idempotent=False,
        timeout_ms=5000,
        circuit_breaker_dependency="kafka",
    )

    def __init__(self, audit_producer: AuditProducer | None = None) -> None:
        self.audit_producer = audit_producer

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Emit a human escalation event.

        input_data keys:
          - reason (str): Why escalation is needed
          - context_summary (str): Summary of what was being analyzed
          - severity (str): low|medium|high|critical (default 'medium')
        """
        start = time.monotonic()
        reason = input_data.get("reason", "Unspecified")
        context_summary = input_data.get("context_summary", "")
        severity = input_data.get("severity", "medium")

        escalation_id = str(uuid.uuid4())

        escalation_payload = {
            "escalation_id": escalation_id,
            "tenant_id": context.tenant_id,
            "session_id": context.session_id,
            "reason": reason,
            "context_summary": context_summary[:2000],
            "severity": severity,
            "user_role": context.user_role,
        }

        # Emit via Kafka audit topic
        if self.audit_producer:
            try:
                await self.audit_producer.send_audit(
                    job_id=context.session_id,
                    tenant_id=context.tenant_id,
                    query=f"ESCALATION: {reason}",
                    sources_count=0,
                    findings_count=0,
                    confidence_score=0.0,
                    data_sources_used=["escalation"],
                )
            except Exception as exc:
                logger.warning("Failed to send escalation event: %s", exc)

        logger.warning(
            "Human escalation raised [%s]: %s (severity=%s, tenant=%s)",
            escalation_id,
            reason,
            severity,
            context.tenant_id,
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "escalation_id": escalation_id,
                "escalation_topic": "market-research-audit-topic",
                "status": "escalated",
                "severity": severity,
                "reason": reason,
            },
            duration_ms=_elapsed(start),
        )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
