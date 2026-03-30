"""Internal event bus for CAA service."""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.kafka_producer import AuditProducer

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """CAA event types (EVT-CAA-001 through EVT-CAA-019)."""

    SESSION_STARTED = "EVT-CAA-001"
    WF1_CONTEXT_LOADED = "EVT-CAA-002"
    WF1_CONTEXT_MISSING = "EVT-CAA-003"
    WF2_CONTEXT_LOADED = "EVT-CAA-004"
    WF2_CONTEXT_MISSING = "EVT-CAA-005"
    COMPANY_CONTEXT_LOADED = "EVT-CAA-006"
    COMPANY_CONTEXT_MISSING = "EVT-CAA-007"
    TAVILY_BENCHMARKS_LOADED = "EVT-CAA-008"
    TAVILY_BENCHMARKS_SKIPPED = "EVT-CAA-009"
    ODOO_DATA_LOADED = "EVT-CAA-010"
    ODOO_DATA_SKIPPED = "EVT-CAA-011"
    RAG_LEARNINGS_LOADED = "EVT-CAA-012"
    RAG_LEARNINGS_SKIPPED = "EVT-CAA-013"
    ARCHITECTURE_SYNTHESIS_STARTED = "EVT-CAA-014"
    ARCHITECTURE_SYNTHESIS_COMPLETED = "EVT-CAA-015"
    BLUEPRINT_SYNTHESIS_COMPLETED = "EVT-CAA-016"
    GCS_UPLOAD_COMPLETED = "EVT-CAA-017"
    GCS_UPLOAD_FAILED = "EVT-CAA-018"
    ESCALATION_TRIGGERED = "EVT-CAA-019"
    SESSION_COMPLETED = "EVT-CAA-020"
    CACHE_HIT = "EVT-CAA-021"
    PREREQUISITE_MISSING = "EVT-CAA-022"
    BUDGET_GUARDRAIL_TRIGGERED = "EVT-CAA-023"
    SPECIAL_AD_CATEGORY_DETECTED = "EVT-CAA-024"


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
