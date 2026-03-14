"""Kafka event schemas for TCIA messaging."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """Real-time trace event for UI updates."""

    job_id: str = ""
    agent: str = "trend-cultural-insights"
    message: str = ""
    status: str = "PROCESSING"
    timestamp: str = ""


class AuditEvent(BaseModel):
    """Audit trail event."""

    event_type: str = ""
    session_id: str = ""
    tenant_id: str = ""
    timestamp: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class OpportunityAlertEvent(BaseModel):
    """Opportunity alert event for Kafka streaming."""

    event_type: str = "opportunity.alert"
    tenant_id: str = ""
    alert_id: str = ""
    trend_slug: str = ""
    relevance_score: int = 0
    urgency: str = "this_month"
    recommendation: str = ""
    affected_personas: list[str] = Field(default_factory=list)
    expiry_estimate: str = ""
    timestamp: str = ""


class ScanPayload(BaseModel):
    """Payload for scheduled scan commands."""

    scan_type: Literal["daily_scan", "weekly_comprehensive"] = "daily_scan"
    industry: str = ""
    focus_areas: list[str] = Field(default_factory=list)


class ScheduledScanCommand(BaseModel):
    """Kafka command for scheduled trend scans."""

    command_type: Literal[
        "scheduled_trend_scan", "scheduled_trend_report"
    ] = "scheduled_trend_scan"
    tenant_id: str = ""
    payload: ScanPayload = Field(default_factory=ScanPayload)
    idempotency_key: str = ""
    timestamp: str = ""
