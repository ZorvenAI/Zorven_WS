"""Internal event bus for Campaign Optimization Agent.

Event codes EVT-050 through EVT-061 cover the full optimization lifecycle:
tick → analyze → recommend → execute → verify → persist.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.kafka_producer import AuditProducer

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """COA event types (EVT-050 through EVT-061)."""

    TICK_STARTED = "EVT-050"
    CAMPAIGN_ANALYZED = "EVT-051"
    RECOMMENDATION_CREATED = "EVT-052"
    ACTION_AUTO_EXECUTED = "EVT-053"
    ACTION_APPROVED = "EVT-054"
    ACTION_REJECTED = "EVT-055"
    ACTION_EXPIRED = "EVT-056"
    FATIGUE_DETECTED = "EVT-057"
    CREATIVE_REFRESH_REQUESTED = "EVT-058"
    SPEND_MILESTONE = "EVT-059"
    GUARDRAIL_TRIGGERED = "EVT-060"
    VERIFICATION_FAILED = "EVT-061"


class EventEmitter:
    """Emits structured events to Kafka audit topic."""

    def __init__(self, audit_producer: AuditProducer):
        self._audit = audit_producer

    async def emit(
        self,
        event_type: EventType,
        tenant_id: str = "",
        campaign_id: str = "",
        data: dict[str, Any] | None = None,
    ):
        """Emit an event."""
        event = {
            "event_type": event_type.value,
            "event_name": event_type.name,
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        logger.debug("Event: %s (%s)", event_type.name, event_type.value)
        await self._audit.send_event(event)
