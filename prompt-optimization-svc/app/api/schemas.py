"""Pydantic request/response models for prompt-optimization-svc."""

from typing import Any, Literal, Optional

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

    status: str = Field(default="healthy", description="healthy | degraded | unhealthy")
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
        default_factory=dict,
        description="Optional metadata (workflow, model_target, etc.)",
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


class PromptMetadata(BaseModel):
    """Structured metadata block per §3.4."""

    workflow: str = Field(..., description="e.g. wf1, wf2, wf3")
    agent_code: str = Field(..., description="e.g. mra, cga, bpa")
    agent_port: int = Field(..., description="Agent service port, e.g. 8021")
    skill: str = Field(..., description="Skill name, e.g. landscape, system")
    model_target: str = Field(
        default="claude-sonnet-4-6", description="Target LLM model"
    )
    optimization_group: str = Field(..., description="e.g. wf1-discovery-pipeline")
    tenant_overridable: bool = Field(
        default=True, description="Whether tenants can customize this prompt"
    )
    optimization_priority: str = Field(
        default="MEDIUM", description="CRITICAL | HIGH | MEDIUM | LOW"
    )
    last_optimized: Optional[str] = Field(
        default=None, description="ISO timestamp of last optimization"
    )
    optimization_run_id: Optional[str] = Field(
        default=None, description="MLflow run ID of last optimization"
    )


class PromptDetailResponse(BaseModel):
    """Response for GET /v1/prompts/{name} — full prompt detail with metadata."""

    name: str
    version: int
    template: str
    state: str
    metadata: PromptMetadata
    tags: dict[str, str] = Field(default_factory=dict)


class PromptSummary(BaseModel):
    """Summary entry for GET /v1/prompts list."""

    name: str
    version: int
    state: str
    agent_code: str
    workflow: str


class PromptListResponse(BaseModel):
    """Response for GET /v1/prompts."""

    prompts: list[PromptSummary]
    total: int


class PromptTransitionRequest(BaseModel):
    """Request body for lifecycle transitions."""

    target_state: str = Field(
        ..., description="Target state: STAGING, CANARY, PRODUCTION, etc."
    )
    tenant_id: Optional[str] = Field(
        default=None, description="Tenant ID for scoped transitions"
    )


class PromptTransitionResponse(BaseModel):
    """Response for lifecycle transition endpoints."""

    name: str
    version: int
    from_state: str
    to_state: str
    success: bool
    message: str = ""


class ProductionPromptResponse(BaseModel):
    """Response for GET /v1/prompts/{name}/production."""

    name: str
    version: int
    template: str
    state: str
    tenant_id: Optional[str] = None
    tags: dict[str, str] = Field(default_factory=dict)


class SeedResponse(BaseModel):
    """Response for POST /v1/prompts/seed."""

    created: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[str] = Field(default_factory=list)


class JointOptimizationResponse(BaseModel):
    """Response for POST /v1/optimize/group/{group_name}."""

    group_name: str
    mlflow_run_id: str = ""
    prompt_count: int = 0
    overall_score: float = 0.0
    candidates_evaluated: int = 0
    promoted_as_set: bool = False
    duration_seconds: float = 0.0
    error: Optional[str] = None


class RunStatusResponse(BaseModel):
    """Response for GET /v1/optimize/runs/{run_id}."""

    run_id: str
    state: str
    prompt_name: str = ""
    agent_code: str = ""
    error_message: str = ""
    deferred_until: Optional[str] = None
    updated_at: Optional[str] = None


class RunListResponse(BaseModel):
    """Response for GET /v1/optimize/runs."""

    runs: list[RunStatusResponse]
    total: int


# ── Golden Dataset schemas ──


class GoldenDatasetResponse(BaseModel):
    """Response for a single golden dataset entry."""

    id: int
    prompt_name: str
    agent_code: str
    source: str
    metadata_extra: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class DatasetStatsResponse(BaseModel):
    """Response for GET /v1/datasets/stats."""

    per_agent: dict[str, int] = Field(default_factory=dict)
    per_source: dict[str, int] = Field(default_factory=dict)
    industry_count: int = 0
    total: int = 0


class DatasetSeedResponse(BaseModel):
    """Response for POST /v1/datasets/seed."""

    created: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[str] = Field(default_factory=list)


class SyntheticGenerateRequest(BaseModel):
    """Request for POST /v1/datasets/generate."""

    industry: str = Field(..., description="Industry vertical")
    brand_maturity: Literal["new", "emerging", "established"] = Field(
        default="new", description="Brand stage"
    )
    objective: str = Field(
        default="Drive brand awareness", description="Business objective"
    )
    prompt_name: str = Field(
        default="zorven-wf1-mra-system", description="Target prompt"
    )
    agent_code: str = Field(default="mra", description="Agent code")
    count: int = Field(default=1, ge=1, le=10, description="Number to generate")


class SyntheticGenerateResponse(BaseModel):
    """Response for POST /v1/datasets/generate."""

    examples: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class DatasetSizeConfigRequest(BaseModel):
    """Request for PUT /v1/config/dataset-size."""

    size: int = Field(..., ge=3, le=50, description="Dataset size [3, 50]")


class DatasetSizeConfigResponse(BaseModel):
    """Response for dataset size configuration."""

    tenant_id: str = ""
    size: int = 10
    min_size: int = 3
    max_size: int = 50


# ── Approval schemas ──


class ApprovalRequest(BaseModel):
    """Request for POST /v1/optimize/runs/{run_id}/approve."""

    approved_by: str = Field(..., description="User/role approving the run")


class RejectionRequest(BaseModel):
    """Request for POST /v1/optimize/runs/{run_id}/reject."""

    approved_by: str = Field(..., description="User/role rejecting the run")
    reason: str = Field(..., description="Rejection reason")


class ApprovalResponse(BaseModel):
    """Response for approval/rejection actions."""

    run_id: str
    decision: Literal["approved", "rejected"]
    approved_by: str
    decided_at: str


# ── Tenant override schemas ──


class TenantOverrideRequest(BaseModel):
    """Request for POST /v1/prompts/{name}/tenant-overrides."""

    template: str = Field(..., min_length=1, description="Override prompt template")
    tenant_id: str = Field(..., min_length=1, description="Tenant identifier")


class TenantOverrideResponse(BaseModel):
    """Response for tenant override operations."""

    prompt_name: str
    tenant_id: str
    version: int = 0
    template: str = ""
    state: str = "TENANT_OVERRIDE"


class TenantOptimizationConfig(BaseModel):
    """Full tenant optimization configuration."""

    tenant_id: str = ""
    prompt_optimization_enabled: bool = True
    prompt_auto_promotion: bool = True
    prompt_optimization_model: str = "claude-sonnet-4-6"
    prompt_optimization_budget: int = 200
    prompt_promotion_threshold: float = 0.05
    prompt_cache_ttl_seconds: int = 300
    golden_dataset_default_size: int = 10
    wf3_optimization_schedule: str = "monthly"


class TenantConfigUpdateRequest(BaseModel):
    """Partial update for tenant optimization config."""

    prompt_optimization_enabled: Optional[bool] = None
    prompt_auto_promotion: Optional[bool] = None
    prompt_optimization_model: Optional[str] = None
    prompt_optimization_budget: Optional[int] = None
    prompt_promotion_threshold: Optional[float] = None
    prompt_cache_ttl_seconds: Optional[int] = None
    golden_dataset_default_size: Optional[int] = None
    wf3_optimization_schedule: Optional[str] = None
