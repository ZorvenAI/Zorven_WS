"""Command schemas for Kafka consumer — scheduled competitive scans."""

from pydantic import BaseModel, Field


class ScheduledScanPayload(BaseModel):
    """Payload for a scheduled competitive scan command."""

    brand_description: str = Field(default="", description="Brand to analyze")
    industry: str = Field(default="", description="Industry context")
    geography: str = Field(default="", description="Geographic focus")
    max_competitors: int = Field(default=10, description="Max competitors to discover")
    scan_type: str = Field(
        default="incremental",
        description="Scan type: 'full' or 'incremental'",
    )


class ScheduledScanCommand(BaseModel):
    """Kafka command for triggering a scheduled competitive scan."""

    command_id: str = Field(..., description="Unique command identifier")
    command_type: str = Field(
        default="scheduled_competitive_scan",
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
