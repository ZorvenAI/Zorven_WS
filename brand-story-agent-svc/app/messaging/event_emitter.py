"""Internal event bus for BSA service."""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.kafka_producer import AuditProducer

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """BSA event types (EVT-BSA-001 through EVT-BSA-020)."""

    SESSION_STARTED = "EVT-BSA-001"
    WF1_CONTEXT_LOADED = "EVT-BSA-002"
    WF1_CONTEXT_MISSING = "EVT-BSA-003"
    BPA_CONTEXT_LOADED = "EVT-BSA-004"
    BPA_CONTEXT_MISSING = "EVT-BSA-005"
    BPV_CONTEXT_LOADED = "EVT-BSA-006"
    BPV_CONTEXT_MISSING = "EVT-BSA-007"
    BAA_CONTEXT_LOADED = "EVT-BSA-008"
    BAA_CONTEXT_MISSING = "EVT-BSA-009"
    NTA_CONTEXT_LOADED = "EVT-BSA-010"
    NTA_CONTEXT_MISSING = "EVT-BSA-011"
    ANALYSIS_PHASE_STARTED = "EVT-BSA-012"
    ANALYSIS_PHASE_COMPLETED = "EVT-BSA-013"
    NARRATIVES_GENERATED = "EVT-BSA-014"
    GCS_UPLOAD_COMPLETED = "EVT-BSA-015"
    GCS_UPLOAD_FAILED = "EVT-BSA-016"
    ESCALATION_TRIGGERED = "EVT-BSA-017"
    SESSION_COMPLETED = "EVT-BSA-018"
    CACHE_HIT = "EVT-BSA-019"
    PREREQUISITE_MISSING = "EVT-BSA-020"


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
