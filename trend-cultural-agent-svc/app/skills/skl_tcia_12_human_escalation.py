"""SKL-TCIA-12: Human Escalation.

Emits escalation events for human review when confidence is low
or harmful content is detected.
"""

import logging
import time
import uuid
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class HumanEscalation(BaseSkill):
    """Emit escalation events for human review."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-12",
        name="human_escalation",
        description="Escalate to human review when confidence is low or harmful content detected",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=5000,
        circuit_breaker_dependency="kafka",
    )

    def __init__(self, audit_producer: Any = None) -> None:
        self._audit = audit_producer

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()

        escalation_id = str(uuid.uuid4())
        reason = input_data.get("reason", "unspecified")
        severity = input_data.get("severity", "MEDIUM")
        affected_trends = input_data.get("affected_trends", [])

        event = {
            "event_type": "escalation.triggered",
            "escalation_id": escalation_id,
            "reason": reason,
            "severity": severity,
            "affected_trends": affected_trends,
            "tenant_id": context.tenant_id,
            "session_id": context.session_id,
        }

        if self._audit:
            try:
                await self._audit.send_event(event)
            except Exception as exc:
                logger.warning("Failed to emit escalation event: %s", exc)

        logger.info(
            "Escalation %s: reason=%s severity=%s trends=%d",
            escalation_id,
            reason,
            severity,
            len(affected_trends),
        )

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"escalation_id": escalation_id, "status": "emitted"},
            duration_ms=elapsed,
        )
