"""Pydantic schemas for ILA API."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    """Orchestrator → ILA execute payload.

    Mirrors the wrapper produced by pipeline-orchestrator-svc external nodes.
    """

    job_id: str
    tenant_id: str | None = None
    pipeline_id: str | None = None
    user_prompt: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class LearningOut(BaseModel):
    learning_id: str
    category: Literal["audience", "messaging", "creative", "funnel", "competitive"]
    headline: str
    detail: dict[str, Any] = Field(default_factory=dict)
    confidence: int = Field(ge=0, le=100)
    impact: Literal["LOW", "MEDIUM", "HIGH"]
    target_workflow: Literal["WF1", "WF2", "WF3"]
    target_agent: str


class IntelligenceReport(BaseModel):
    intelligence_id: str
    campaign_id: str | None = None
    brand_context_id: str = ""
    mode: Literal["store_only", "auto_trigger"] = "store_only"
    trigger_source: str = "manual"
    summary: str = ""
    learnings: list[LearningOut] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    auto_reruns_triggered: int = 0
    rag_writes: int = 0


class ExecuteResponse(BaseModel):
    status: Literal["success", "skipped", "error"] = "success"
    job_id: str
    intelligence_report: IntelligenceReport
    node_id: str = "campaign_intelligence"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str = "0.1.0"
