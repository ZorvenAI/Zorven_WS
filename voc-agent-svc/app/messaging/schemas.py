"""Kafka message schemas for the Voice of Customer Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """Real-time node progress event for agent-trace-topic."""

    job_id: str = ""
    node_id: str = "voice_of_customer"
    status: str = ""  # started | completed | error
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    """Audit trail event for voc-audit-topic."""

    event_type: str = ""
    event_name: str = ""
    tenant_id: str = ""
    session_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class InsightAlertEvent(BaseModel):
    """VoC insight alert for voc-insights-topic."""

    tenant_id: str = ""
    alert_id: str = ""
    alert_type: str = ""  # sentiment_shift | nps_drop | theme_surge | critical
    severity: str = ""  # low | medium | high | critical
    title: str = ""
    description: str = ""
    affected_personas: list[str] = Field(default_factory=list)
    recommendation: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ScanPayload(BaseModel):
    """Payload for scheduled scan commands."""

    tenant_id: str = ""
    company_name: str = ""
    industry: str = ""
    focus_areas: list[str] = Field(default_factory=list)


class ScheduledScanCommand(BaseModel):
    """Command schema for agent.commands.voice-of-customer-agent."""

    scan_type: str = "full"  # full | incremental
    payload: ScanPayload = Field(default_factory=ScanPayload)


class OdooEvent(BaseModel):
    """Odoo event from odoo.events.<tid> topic."""

    event_type: str = ""  # ticket_created | ticket_updated | survey_completed | chatter_message
    model: str = ""  # project.task | helpdesk.ticket | survey.user_input | mail.message
    record_id: int = 0
    tenant_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""
