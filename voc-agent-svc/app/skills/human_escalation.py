"""SKL-VoCA-14: Human Escalation.

Emits escalation events for human review via the AuditProducer
(voc-audit-topic) when critical conditions are detected.

Triggers:
- Critical negative sentiment (>60% negative)
- NPS drop >10 points
- PII leak detected
- Insufficient data for reliable analysis
"""

import json
import logging
import time
import uuid
from typing import Any

from app.messaging.kafka_producer import AuditProducer
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class HumanEscalation(BaseSkill):
    """Emit escalation events for human review of VoC analysis."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-14",
        name="human_escalation",
        description=(
            "Trigger human escalation for critical negative sentiment, "
            "NPS drop >10 points, PII leak, or insufficient data. "
            "Emits escalation details to voc-audit-topic via AuditProducer."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        idempotent=True,
        timeout_ms=10000,
        circuit_breaker_dependency="kafka",
    )

    def __init__(self, audit_producer: AuditProducer | None = None) -> None:
        self._audit = audit_producer

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Evaluate escalation triggers and emit event if needed.

        input_data keys:
          - reason (str): Why escalation is needed
          - severity (str): low, medium, high, critical
          - trigger_type (str): One of critical_negative_sentiment,
              nps_drop, pii_leak, insufficient_data
          - sentiment (dict): Sentiment breakdown (optional)
          - nps_data (dict): NPS data with score and previous_score (optional)
          - context_summary (str): Brief summary for human reviewer (optional)
          - affected_channels (list[str]): Impacted feedback channels (optional)
        """
        start = time.monotonic()

        try:
            escalation_id = str(uuid.uuid4())
            reason = input_data.get("reason", "Automated escalation")
            severity = input_data.get("severity", "medium")
            trigger_type = input_data.get("trigger_type", "unspecified")
            context_summary = input_data.get("context_summary", "")
            sentiment = input_data.get("sentiment", {})
            nps_data = input_data.get("nps_data", {})
            affected_channels = input_data.get("affected_channels", [])

            # Build escalation event
            escalation_event: dict[str, Any] = {
                "event_type": "voc.escalation.triggered",
                "event_name": "human_escalation",
                "escalation_id": escalation_id,
                "trigger_type": trigger_type,
                "reason": reason,
                "severity": severity,
                "context_summary": context_summary[:1000],
                "tenant_id": context.tenant_id,
                "session_id": context.session_id,
                "user_role": context.user_role,
                "affected_channels": affected_channels,
            }

            # Attach trigger-specific data
            if trigger_type == "critical_negative_sentiment" and sentiment:
                escalation_event["sentiment_breakdown"] = sentiment
            elif trigger_type == "nps_drop" and nps_data:
                escalation_event["nps_current"] = nps_data.get("score")
                escalation_event["nps_previous"] = nps_data.get(
                    "previous_score"
                )
                escalation_event["nps_drop"] = (
                    (nps_data.get("previous_score") or 0)
                    - (nps_data.get("score") or 0)
                )
            elif trigger_type == "pii_leak":
                escalation_event["pii_types_detected"] = input_data.get(
                    "pii_types_detected", []
                )
            elif trigger_type == "insufficient_data":
                escalation_event["data_coverage_score"] = input_data.get(
                    "data_coverage_score", 0.0
                )
                escalation_event["minimum_required"] = input_data.get(
                    "minimum_required", 0.0
                )

            # Emit to audit producer (voc-audit-topic)
            emitted = False
            if self._audit:
                try:
                    await self._audit.send_event(
                        event_type="voc.escalation.triggered",
                        event_name="human_escalation",
                        tenant_id=context.tenant_id,
                        session_id=context.session_id,
                        data=escalation_event,
                    )
                    emitted = True
                    logger.info(
                        "Escalation %s emitted for tenant %s: "
                        "trigger=%s severity=%s reason=%s",
                        escalation_id,
                        context.tenant_id,
                        trigger_type,
                        severity,
                        reason,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to emit escalation event %s: %s",
                        escalation_id,
                        exc,
                    )
            else:
                logger.debug(
                    "Escalation %s (no producer): trigger=%s severity=%s",
                    escalation_id,
                    trigger_type,
                    severity,
                )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "escalated": True,
                    "reason": reason,
                    "severity": severity,
                    "escalation_id": escalation_id,
                    "trigger_type": trigger_type,
                    "emitted": emitted,
                },
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.error(
                "Human escalation failed for tenant %s: %s",
                context.tenant_id,
                exc,
            )
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _elapsed(start: float) -> float:
    """Calculate elapsed time in milliseconds."""
    return (time.monotonic() - start) * 1000
