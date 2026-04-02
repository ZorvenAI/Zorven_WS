"""Pydantic v2 request/response models for the Ad Publishing Agent."""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class TenantContext(BaseModel):
    """Tenant context passed from the orchestrator."""

    tenant_id: str = ""
    company_name: str = ""
    user_role: str = "VIEWER"
    meta_access_token: str = ""
    meta_ad_account_id: str = ""
    meta_page_id: str = ""
    meta_business_id: str = ""
    meta_ads_sandbox_mode: bool = True


class ExecuteRequest(BaseModel):
    """Request to run phases 1-4 of ad publishing."""

    input_prompt: str = ""
    input_context: dict[str, Any] = Field(default_factory=dict)
    tenant_context: TenantContext | dict[str, Any] = Field(
        default_factory=dict
    )
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    """Request to process a human approval decision."""

    approval_request_id: str
    decision: Literal["approve_all", "approve_selected", "reject"]
    approved_ad_sets: list[str] | None = None
    feedback: str = ""
    production_confirmed: bool = False


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------


class ApprovalResponse(BaseModel):
    """Response from the approval endpoint."""

    approval_request_id: str = ""
    status: str = ""
    published_campaign: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    execution_time_ms: int = 0


class AdPubResponse(BaseModel):
    """Response from the execute endpoint."""

    query: str = ""
    status: str = "awaiting_approval"
    approval_request_id: str = ""
    preview_data: dict[str, Any] = Field(default_factory=dict)
    is_production: bool = False
    sandbox_mode: bool = True
    plan_warnings: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    preparation_time_ms: int = 0
    execution_time_ms: int = 0
