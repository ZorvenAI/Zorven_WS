"""Event catalog and emitter for the Trend & Cultural Insights Agent."""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # Standard events (EVT-001..014)
    SESSION_STARTED = "session.started"
    INPUT_RECEIVED = "input.received"
    INPUT_GUARDRAIL_PASSED = "input.guardrail.passed"
    PLAN_CREATED = "plan.created"
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    OUTPUT_GUARDRAIL_APPLIED = "output.guardrail.applied"
    RESPONSE_SENT = "response.sent"
    ERROR_OCCURRED = "error.occurred"
    SESSION_COMPLETED = "session.completed"
    CIRCUIT_BREAKER_OPENED = "circuit_breaker.opened"
    RATE_LIMIT_HIT = "rate_limit.hit"
    ESCALATION_TRIGGERED = "escalation.triggered"

    # TCIA-specific events (EVT-015..018)
    TREND_REGISTRY_UPDATED = "trend.registry.updated"
    TREND_VELOCITY_CHANGED = "trend.velocity.changed"
    OPPORTUNITY_ALERT_EMITTED = "opportunity.alert.emitted"
    SCHEDULED_SCAN_COMPLETED = "scheduled.scan.completed"


class EventEmitter:
    """Emit structured events to the audit Kafka producer."""

    def __init__(self, audit_producer: Any = None) -> None:
        self._audit_producer = audit_producer

    async def emit(
        self,
        event_type: EventType,
        *,
        session_id: str = "",
        tenant_id: str = "",
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Emit an event to the audit trail."""
        event = {
            "event_type": event_type.value,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": detail or {},
        }
        logger.info(
            "Event %s: session=%s tenant=%s",
            event_type.value,
            session_id,
            tenant_id,
        )
        if self._audit_producer:
            try:
                await self._audit_producer.send_event(event)
            except Exception as exc:
                logger.warning("Failed to emit event %s: %s", event_type.value, exc)
