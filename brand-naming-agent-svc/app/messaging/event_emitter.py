"""Internal event bus for NTA service."""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.kafka_producer import AuditProducer

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """NTA event types (EVT-NTA-001 through EVT-NTA-014)."""

    SESSION_STARTED = "EVT-NTA-001"
    WF1_CONTEXT_LOADED = "EVT-NTA-002"
    WF1_CONTEXT_MISSING = "EVT-NTA-003"
    BPA_CONTEXT_LOADED = "EVT-NTA-004"
    BPA_CONTEXT_MISSING = "EVT-NTA-005"
    BPV_CONTEXT_LOADED = "EVT-NTA-006"
    BPV_CONTEXT_MISSING = "EVT-NTA-007"
    BAA_CONTEXT_LOADED = "EVT-NTA-008"
    BAA_CONTEXT_MISSING = "EVT-NTA-009"
    ANALYSIS_PHASE_STARTED = "EVT-NTA-010"
    ANALYSIS_PHASE_COMPLETED = "EVT-NTA-011"
    NAMES_GENERATED = "EVT-NTA-012"
    ESCALATION_TRIGGERED = "EVT-NTA-013"
    SESSION_COMPLETED = "EVT-NTA-014"


class EventEmitter:
    """Emits structured events to Kafka audit topic."""

    def __init__(self, audit_producer: AuditProducer):
        self._audit = audit_producer

    async def emit(
        self,
        event_type: EventType,
        tenant_id: str = "",
        job_id: str = "",
        data: dict[str, Any] | None = None,
    ):
        """Emit an event."""
        event = {
            "event_type": event_type.value,
            "event_name": event_type.name,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        logger.debug("Event: %s (%s)", event_type.name, event_type.value)
        await self._audit.send_event(event)
