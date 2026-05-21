"""Pydantic request/response models for prompt-optimization-svc."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class DependencyStatus(BaseModel):
    """Health status for a single dependency."""

    name: str
    status: str = Field(description="up | down | disabled")
    latency_ms: Optional[float] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Aggregate health check response."""

    status: str = Field(
        default="healthy", description="healthy | degraded | unhealthy"
    )
    dependencies: list[DependencyStatus] = Field(default_factory=list)


class TenantContext(BaseModel):
    """Tenant isolation context passed by orchestrator."""

    model_config = {"extra": "allow"}

    tenant_id: str = ""
    user_role: str = "EDITOR"


class ExecuteRequest(BaseModel):
    """Request body for POST /v1/execute."""

    input_prompt: str = Field(..., description="The user's query")
    input_context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )
    tenant_context: TenantContext | dict[str, Any] = Field(
        default_factory=dict, description="Tenant isolation data"
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Node configuration"
    )
    previous_outputs: dict[str, Any] = Field(
        default_factory=dict, description="Upstream node outputs"
    )


class ExecuteResponse(BaseModel):
    """Response for POST /v1/execute (stub for future epics)."""

    status: str = "not_implemented"
    message: str = "Prompt optimization endpoints will be available in EPIC-2+"
