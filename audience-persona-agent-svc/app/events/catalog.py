"""Event catalog and emitter for the Audience Persona Agent.

18 event types (EVT-001 through EVT-018):
- EVT-001..014: Standard agent events (shared with MRA/CIA)
- EVT-015: persona.registry.updated
- EVT-016: persona.evolution.detected
- EVT-017: odoo.survey.extracted
- EVT-018: odoo.crm.extracted
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """All 18 APA event types."""

    # Standard agent events (EVT-001..014)
    SESSION_STARTED = "session.started"  # EVT-001
    INPUT_RECEIVED = "input.received"  # EVT-002
    INPUT_GUARDRAIL_PASSED = "input.guardrail.passed"  # EVT-003
    PLAN_CREATED = "plan.created"  # EVT-004
    TOOL_CALLED = "tool.called"  # EVT-005
    TOOL_COMPLETED = "tool.completed"  # EVT-006
    TOOL_FAILED = "tool.failed"  # EVT-007
    OUTPUT_GUARDRAIL_APPLIED = "output.guardrail.applied"  # EVT-008
    RESPONSE_SENT = "response.sent"  # EVT-009
    ERROR_OCCURRED = "error.occurred"  # EVT-010
    SESSION_COMPLETED = "session.completed"  # EVT-011
    CIRCUIT_BREAKER_OPENED = "circuit_breaker.opened"  # EVT-012
    RATE_LIMIT_HIT = "rate_limit.hit"  # EVT-013
    ESCALATION_TRIGGERED = "escalation.triggered"  # EVT-014

    # APA-specific events (EVT-015..018)
    PERSONA_REGISTRY_UPDATED = "persona.registry.updated"  # EVT-015
    PERSONA_EVOLUTION_DETECTED = "persona.evolution.detected"  # EVT-016
    ODOO_SURVEY_EXTRACTED = "odoo.survey.extracted"  # EVT-017
    ODOO_CRM_EXTRACTED = "odoo.crm.extracted"  # EVT-018


class EventEmitter:
    """Emits structured events to logs and optionally Kafka."""

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
        """Emit an event to structured logs and optionally Kafka."""
        event = {
            "event_type": event_type.value,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": detail or {},
        }

        logger.info(
            "Event %s: session=%s tenant=%s detail=%s",
            event_type.value,
            session_id,
            tenant_id,
            detail,
        )

        if self._audit_producer:
            try:
                await self._audit_producer.send_event(event)
            except Exception as exc:
                logger.warning(
                    "Failed to publish event %s to Kafka: %s",
                    event_type.value,
                    exc,
                )
