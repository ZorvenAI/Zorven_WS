"""Event catalog — EVT-001 through EVT-014 per design document.

All events are emitted to Kafka audit topic (when available) and structured logger.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.messaging.kafka_producer import AuditProducer

logger = logging.getLogger(__name__)


class EventCatalog:
    """Event ID constants and metadata."""

    SESSION_STARTED = "EVT-001"
    INPUT_RECEIVED = "EVT-002"
    GUARDRAIL_INPUT = "EVT-003"
    PLAN_CREATED = "EVT-004"
    TOOL_CALLED = "EVT-005"
    TOOL_COMPLETED = "EVT-006"
    TOOL_FAILED = "EVT-007"
    GUARDRAIL_OUTPUT = "EVT-008"
    RESPONSE_SENT = "EVT-009"
    SESSION_ESCALATED = "EVT-010"
    SESSION_COMPLETED = "EVT-011"
    CIRCUIT_BREAKER_OPENED = "EVT-012"
    MEMORY_COMPRESSED = "EVT-013"
    RBAC_DECISION = "EVT-014"

    DESCRIPTIONS: dict[str, str] = {
        "EVT-001": "agent.session.started",
        "EVT-002": "agent.input.received",
        "EVT-003": "guardrail.input.triggered",
        "EVT-004": "agent.plan.created",
        "EVT-005": "agent.tool.called",
        "EVT-006": "agent.tool.completed",
        "EVT-007": "agent.tool.failed",
        "EVT-008": "guardrail.output.triggered",
        "EVT-009": "agent.response.sent",
        "EVT-010": "agent.session.escalated",
        "EVT-011": "agent.session.completed",
        "EVT-012": "circuit_breaker.opened",
        "EVT-013": "memory.compression.applied",
        "EVT-014": "rbac.decision",
    }


class EventEmitter:
    """Emits events to Kafka audit topic + structured logger."""

    def __init__(
        self,
        audit_producer: AuditProducer | None = None,
    ) -> None:
        self.audit_producer = audit_producer

    async def emit(
        self,
        event_id: str,
        tenant_id: str,
        session_id: str,
        payload: dict[str, Any] | None = None,
        outcome: str = "SUCCESS",
    ) -> None:
        """Emit a structured event."""
        event_name = EventCatalog.DESCRIPTIONS.get(event_id, "unknown")
        event_data = {
            "event_id": event_id,
            "event_name": event_name,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "outcome": outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }

        # Always log structurally
        logger.info(
            "Event %s (%s) tenant=%s session=%s outcome=%s",
            event_id,
            event_name,
            tenant_id,
            session_id,
            outcome,
        )

        # Emit to Kafka audit topic (non-fatal)
        if self.audit_producer:
            try:
                await self.audit_producer.send_audit(
                    job_id=session_id,
                    tenant_id=tenant_id,
                    query=f"{event_id}:{event_name}",
                    sources_count=0,
                    findings_count=0,
                    confidence_score=0.0,
                    data_sources_used=[event_id],
                )
            except Exception as exc:
                logger.warning("Failed to emit event %s to Kafka: %s", event_id, exc)
