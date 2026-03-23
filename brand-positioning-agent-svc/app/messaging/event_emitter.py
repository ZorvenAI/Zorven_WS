"""Event catalog and emitter for the Brand Positioning Agent.

EVT-BPA-001 through EVT-BPA-010 for positioning lifecycle events.
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """BPA event types."""

    # Session lifecycle
    SESSION_STARTED = "EVT-BPA-001"
    SESSION_COMPLETED = "EVT-BPA-002"

    # Research phase
    WF1_CONTEXT_LOADED = "EVT-BPA-003"
    WF1_CONTEXT_MISSING = "EVT-BPA-004"

    # Synthesis phase
    CANDIDATES_GENERATED = "EVT-BPA-005"
    CANVAS_BUILT = "EVT-BPA-006"
    MAPS_GENERATED = "EVT-BPA-007"
    DIFFERENTIATION_BUILT = "EVT-BPA-008"

    # Persistence
    STRATEGY_PERSISTED = "EVT-BPA-009"

    # Escalation
    HUMAN_ESCALATION = "EVT-BPA-010"


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
