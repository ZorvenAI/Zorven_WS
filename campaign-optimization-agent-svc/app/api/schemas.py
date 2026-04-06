"""Pydantic v2 request/response models for the Campaign Optimization Agent."""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    """Request to approve/reject/modify a recommendation."""

    recommendation_id: str
    decision: Literal["approve", "reject", "modify"]
    modified_values: dict[str, Any] | None = None
    feedback: str = ""
    approved_by: str = ""
    user_role: str = "VIEWER"


class BatchApprovalRequest(BaseModel):
    """Request to batch-approve all pending recommendations for a campaign."""

    campaign_id: str
    tenant_id: str
    approved_by: str = ""
    user_role: str = "ADMIN"


class TriggerTickRequest(BaseModel):
    """Request to manually trigger an optimization tick."""

    campaign_age_min_days: int | None = None
    campaign_age_max_days: int | None = None


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------


class ApprovalResponse(BaseModel):
    """Response from the approval endpoint."""

    recommendation_id: str = ""
    status: str = ""
    executed: bool = False
    execution_result: dict[str, Any] | None = None


class RecommendationResponse(BaseModel):
    """Response representing an optimization recommendation."""

    recommendation_id: str = ""
    tenant_id: str = ""
    campaign_id: str = ""
    ad_set_id: str = ""
    ad_id: str = ""
    action_type: str = ""
    entity_type: str = ""
    entity_id: str = ""
    current_values: dict[str, Any] = Field(default_factory=dict)
    proposed_values: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    projected_impact: dict[str, Any] = Field(default_factory=dict)
    priority: str = "medium"
    status: str = "pending"
    requires_approval: bool = True
    created_at: str = ""
    expires_at: str = ""


class CampaignPerformanceResponse(BaseModel):
    """Response with current campaign performance metrics."""

    campaign_id: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    health: str = ""
    trends: dict[str, Any] = Field(default_factory=dict)


class TickStatusResponse(BaseModel):
    """Response from a manual tick trigger."""

    tick_id: str = ""
    campaigns_processed: int = 0
    recommendations_generated: int = 0
    actions_executed: int = 0


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    service: str = "campaign-optimization-agent"
    version: str = "1.0.0"
    celery_status: str = "unknown"
