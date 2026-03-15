"""Event catalog and emitter for the Voice of Customer Agent.

EVT-001 through EVT-021 per design doc Section 8.
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """VoCA event types (EVT-001 through EVT-021)."""

    # Session lifecycle
    SESSION_STARTED = "EVT-001"  # VoC session opened, operating_mode logged
    INPUT_RECEIVED = "EVT-002"  # Prompt + tenant context received
    SESSION_COMPLETED = "EVT-003"  # Final result returned

    # Guardrails
    GUARDRAIL_INPUT_PASSED = "EVT-004"  # Input guardrails passed
    GUARDRAIL_INPUT_BLOCKED = "EVT-005"  # Input guardrails blocked
    GUARDRAIL_PLAN_CHECKED = "EVT-006"  # Plan guardrails evaluated
    GUARDRAIL_OUTPUT_PASSED = "EVT-007"  # Output guardrails passed
    GUARDRAIL_OUTPUT_BLOCKED = "EVT-008"  # Output guardrails blocked

    # Skills
    PLAN_CREATED = "EVT-009"  # Skill execution plan created
    TOOL_CALLED = "EVT-010"  # Skill invocation started
    TOOL_COMPLETED = "EVT-011"  # Skill returned result
    TOOL_FAILED = "EVT-012"  # Skill execution error

    # Circuit breakers
    CIRCUIT_BREAKER_OPENED = "EVT-013"  # CB tripped to OPEN
    CIRCUIT_BREAKER_RECOVERED = "EVT-014"  # CB recovered to CLOSED

    # Response
    RESPONSE_SENT = "EVT-015"  # Response dispatched

    # RBAC
    RBAC_DENIED = "EVT-016"  # Role denied access to skill
    RBAC_ESCALATED = "EVT-017"  # Escalation required

    # Feedback registry
    REGISTRY_UPDATED = "EVT-018"  # Feedback registry updated

    # Operating mode
    MODE_DETECTED = "EVT-019"  # Operating mode determined
    MODE_EXTERNAL_ONLY = "EVT-020"  # External-only mode fallback

    # Ingestion
    INGESTION_MODE_SWITCH = "EVT-021"  # Kafka↔polling mode switched


class EventEmitter:
    """Emits events to audit log and optional Kafka producer."""

    def __init__(self, audit_producer: Any = None) -> None:
        self._audit_producer = audit_producer

    async def emit(
        self,
        event_type: EventType,
        tenant_id: str = "",
        session_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Log and optionally publish an event."""
        logger.info(
            "Event %s [%s] tenant=%s session=%s data=%s",
            event_type.name,
            event_type.value,
            tenant_id,
            session_id,
            data,
        )
        if self._audit_producer:
            try:
                await self._audit_producer.send_event(
                    event_type=event_type.value,
                    event_name=event_type.name,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    data=data or {},
                )
            except Exception as exc:
                logger.warning("Failed to publish event to Kafka: %s", exc)
