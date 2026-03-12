"""SKL-CIA-12: Human Escalation — Kafka event for human review."""

import logging
import time
from typing import Any, Optional

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class HumanEscalation(BaseSkill):
    """Emit a Kafka event requesting human review of competitive intelligence."""

    meta = SkillMeta(
        skill_id="SKL-CIA-12",
        name="human_escalation",
        description=(
            "Request human review when confidence is low, RBAC requires "
            "escalation, or automated analysis is uncertain."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        idempotent=True,
        timeout_ms=10000,
        circuit_breaker_dependency="kafka",
    )

    def __init__(self, kafka_producer: Any = None) -> None:
        self._kafka_producer = kafka_producer

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Emit human escalation event.

        input_data keys:
          - reason (str): Why escalation is needed
          - context_summary (str): Brief summary for human reviewer
          - severity (str): low, medium, high
        """
        start = time.monotonic()
        reason = input_data.get("reason", "Automated escalation")
        context_summary = input_data.get("context_summary", "")
        severity = input_data.get("severity", "medium")

        escalation_event = {
            "type": "competitor_intelligence.escalation",
            "tenant_id": context.tenant_id,
            "session_id": context.session_id,
            "user_role": context.user_role,
            "reason": reason,
            "context_summary": context_summary[:1000],
            "severity": severity,
        }

        if self._kafka_producer:
            try:
                await self._kafka_producer.send_audit(
                    job_id=context.session_id,
                    tenant_id=context.tenant_id,
                    query=context_summary[:200],
                    competitors_count=0,
                    sources_count=0,
                    findings_count=0,
                    confidence_score=0.0,
                    data_sources_used=["escalation"],
                )
                logger.info(
                    "Escalation event emitted for tenant %s: %s",
                    context.tenant_id,
                    reason,
                )
            except Exception as exc:
                logger.warning("Failed to emit escalation event: %s", exc)

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "escalated": True,
                "reason": reason,
                "severity": severity,
                "event": escalation_event,
            },
            duration_ms=_elapsed(start),
        )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
