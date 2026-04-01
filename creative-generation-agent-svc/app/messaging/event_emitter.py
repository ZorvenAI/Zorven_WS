"""Internal event bus for CGA service."""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.kafka_producer import AuditProducer

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """CGA event types (EVT-CGA-001 through EVT-CGA-025)."""

    SESSION_STARTED = "EVT-CGA-001"
    CAA_CONTEXT_LOADED = "EVT-CGA-002"
    CAA_CONTEXT_MISSING = "EVT-CGA-003"
    WF1_CONTEXT_LOADED = "EVT-CGA-004"
    WF1_CONTEXT_MISSING = "EVT-CGA-005"
    WF2_CONTEXT_LOADED = "EVT-CGA-006"
    WF2_CONTEXT_MISSING = "EVT-CGA-007"
    COMPANY_CONTEXT_LOADED = "EVT-CGA-008"
    COMPANY_CONTEXT_MISSING = "EVT-CGA-009"
    CREATIVE_PROFILING_STARTED = "EVT-CGA-010"
    CREATIVE_PROFILING_COMPLETED = "EVT-CGA-011"
    IMAGE_PROMPT_BUILT = "EVT-CGA-012"
    IMAGE_GENERATION_STARTED = "EVT-CGA-013"
    IMAGE_GENERATION_COMPLETED = "EVT-CGA-014"
    IMAGE_GENERATION_FAILED = "EVT-CGA-015"
    COPY_GENERATION_STARTED = "EVT-CGA-016"
    COPY_GENERATION_COMPLETED = "EVT-CGA-017"
    COMPLIANCE_CHECK_COMPLETED = "EVT-CGA-018"
    ASSEMBLY_COMPLETED = "EVT-CGA-019"
    GCS_UPLOAD_COMPLETED = "EVT-CGA-020"
    GCS_UPLOAD_FAILED = "EVT-CGA-021"
    ESCALATION_TRIGGERED = "EVT-CGA-022"
    SESSION_COMPLETED = "EVT-CGA-023"
    CACHE_HIT = "EVT-CGA-024"
    PREREQUISITE_MISSING = "EVT-CGA-025"


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
