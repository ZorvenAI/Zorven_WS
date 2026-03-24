"""Event catalog and emitter for the Brand Architecture Agent.

EVT-BAA-001 through EVT-BAA-012 for architecture lifecycle events.
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """BAA event types."""

    # Session lifecycle
    SESSION_STARTED = "EVT-BAA-001"
    SESSION_COMPLETED = "EVT-BAA-002"

    # Context loading
    WF1_CONTEXT_LOADED = "EVT-BAA-003"
    WF1_CONTEXT_MISSING = "EVT-BAA-004"
    BPA_CONTEXT_LOADED = "EVT-BAA-005"
    BPA_CONTEXT_MISSING = "EVT-BAA-006"
    COMPANY_CONTEXT_LOADED = "EVT-BAA-007"

    # Architecture design
    MODEL_RECOMMENDED = "EVT-BAA-008"
    HIERARCHY_BUILT = "EVT-BAA-009"

    # Persistence
    STRATEGY_PERSISTED = "EVT-BAA-010"

    # Escalation
    HUMAN_ESCALATION = "EVT-BAA-011"

    # Prerequisites missing
    PREREQUISITES_MISSING = "EVT-BAA-012"


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
