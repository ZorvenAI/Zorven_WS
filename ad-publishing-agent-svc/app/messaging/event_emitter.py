"""Internal event bus for Ad Publishing Agent.

Event codes EVT-APA33-001 through EVT-APA33-026 cover the full
lifecycle: session → campaign creation → approval → publish → verify.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.kafka_producer import AuditProducer

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """APA event types (EVT-APA33-001 through EVT-APA33-026)."""

    SESSION_STARTED = "EVT-APA33-001"
    CAMPAIGN_CREATED = "EVT-APA33-002"
    TARGETING_TRANSLATED = "EVT-APA33-003"
    CREATIVE_UPLOADED = "EVT-APA33-004"
    PREVIEW_GENERATED = "EVT-APA33-005"
    APPROVAL_REQUESTED = "EVT-APA33-006"
    APPROVAL_GRANTED = "EVT-APA33-007"
    APPROVAL_REJECTED = "EVT-APA33-008"
    APPROVAL_EXPIRED = "EVT-APA33-009"
    APPROVAL_PARTIAL = "EVT-APA33-010"
    PUBLISH_STARTED = "EVT-APA33-011"
    PUBLISH_COMPLETED = "EVT-APA33-012"
    PUBLISH_FAILED = "EVT-APA33-013"
    VERIFICATION_PASSED = "EVT-APA33-014"
    VERIFICATION_FAILED = "EVT-APA33-015"
    REGISTRY_UPDATED = "EVT-APA33-016"
    ROLLBACK_STARTED = "EVT-APA33-017"
    ROLLBACK_COMPLETED = "EVT-APA33-018"
    CIRCUIT_BREAKER_TRIPPED = "EVT-APA33-019"
    ESCALATION_TRIGGERED = "EVT-APA33-020"
    CONTEXT_LOADED = "EVT-APA33-021"
    CONTEXT_MISSING = "EVT-APA33-022"
    CACHE_HIT = "EVT-APA33-023"
    SESSION_COMPLETED = "EVT-APA33-024"
    AD_SET_CREATED = "EVT-APA33-025"
    AD_ASSEMBLED = "EVT-APA33-026"


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
