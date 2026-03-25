"""Internal event bus for BPV service."""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.kafka_producer import AuditProducer

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """BPV event types (EVT-BPV-001 through EVT-BPV-013)."""

    SESSION_STARTED = "EVT-BPV-001"
    WF1_CONTEXT_LOADED = "EVT-BPV-002"
    WF1_CONTEXT_MISSING = "EVT-BPV-003"
    BPA_CONTEXT_LOADED = "EVT-BPV-004"
    BPA_CONTEXT_MISSING = "EVT-BPV-005"
    BAA_CONTEXT_LOADED = "EVT-BPV-006"
    BAA_CONTEXT_MISSING = "EVT-BPV-007"
    ANALYSIS_PHASE_STARTED = "EVT-BPV-008"
    ANALYSIS_PHASE_COMPLETED = "EVT-BPV-009"
    PERSONALITY_DESIGNED = "EVT-BPV-010"
    PERSONALITY_PERSISTED = "EVT-BPV-011"
    ESCALATION_TRIGGERED = "EVT-BPV-012"
    SESSION_COMPLETED = "EVT-BPV-013"


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
