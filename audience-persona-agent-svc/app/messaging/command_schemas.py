"""Command schemas for Kafka consumer — scheduled persona scans."""

from pydantic import BaseModel, Field


class ScheduledScanPayload(BaseModel):
    """Payload for a scheduled persona scan command."""

    brand_description: str = Field(default="", description="Brand to analyze")
    industry: str = Field(default="", description="Industry context")
    geography: str = Field(default="", description="Geographic focus")
    max_personas: int = Field(default=5, description="Max personas to generate")
    scan_type: str = Field(
        default="incremental",
        description="Scan type: 'full' or 'incremental'",
    )
    refresh_interval_days: int = Field(
        default=30,
        description="How often to refresh (7, 14, 30, or 90 days)",
    )


class ScheduledScanCommand(BaseModel):
    """Kafka command for triggering a scheduled persona scan."""

    command_id: str = Field(..., description="Unique command identifier")
    command_type: str = Field(
        default="scheduled_persona_scan",
        description="Command type",
    )
    tenant_id: str = Field(..., description="Tenant identifier")
    payload: ScheduledScanPayload = Field(
        default_factory=ScheduledScanPayload,
        description="Scan configuration",
    )
    idempotency_key: str = Field(
        default="",
        description="Deduplication key (e.g. schedule:<id>:<date>)",
    )
