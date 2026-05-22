"""Pydantic request/response models for prompt-optimization-svc."""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.logic.prompt_naming import validate_prompt_name


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


class PromptRegistrationRequest(BaseModel):
    """Request body for POST /v1/prompts — register a prompt template."""

    name: str = Field(
        ...,
        description="Prompt name following §3.1: zorven-wf<n>-<agent_code>-<skill>[-<variant>]",
    )
    template: str = Field(..., description="Prompt template text")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata (workflow, model_target, etc.)"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        validate_prompt_name(v)
        return v


class PromptRegistrationResponse(BaseModel):
    """Response for POST /v1/prompts."""

    name: str
    version: int = 1
    status: str = "registered"
    message: str = ""
