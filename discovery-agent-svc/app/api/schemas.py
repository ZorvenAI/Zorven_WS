"""
Pydantic v2 request/response models for discovery-agent-svc.

The ExecuteRequest matches the payload sent by the orchestrator's
ExternalWrapper (pipeline-orchestrator-svc/app/nodes/external_wrapper.py).
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    """Tenant isolation context passed from the orchestrator."""

    tenant_id: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""


class ExecuteRequest(BaseModel):
    """
    Request body for POST /v1/execute.

    Matches the payload the orchestrator's ExternalWrapper sends:
    {input_prompt, input_context, tenant_context, config, previous_outputs}
    """

    input_prompt: str = Field(
        ..., description="The user's query or analysis request"
    )
    input_context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context from the user"
    )
    tenant_context: TenantContext | dict[str, Any] = Field(
        default_factory=dict,
        description="Tenant isolation data (GCS buckets, RAG store)",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Node-level config merged with global_config (e.g. focus, model)",
    )
    previous_outputs: dict[str, Any] = Field(
        default_factory=dict, description="Outputs from upstream pipeline nodes"
    )


class SourceItem(BaseModel):
    """A single source reference (web page, document, etc.)."""

    type: str = Field(
        default="web", description="Source type: web, document, financial"
    )
    title: str = Field(default="", description="Title of the source")
    url: str = Field(default="", description="URL or GCS URI of the source")


class ExecuteResponse(BaseModel):
    """
    Response body for POST /v1/execute.

    Contains search results, scraped content, and structured findings.
    The orchestrator stores this in node_outputs[node_id].
    ManagerNode aggregates 'findings' and 'recommendations'.
    BrandEquityDashboard renders 'sources' as clickable citations.
    """

    query: str = Field(default="", description="The constructed search query")
    sources: list[SourceItem] = Field(
        default_factory=list, description="Source references with type/title/url"
    )
    findings: list[str] = Field(
        default_factory=list, description="Key findings from web research"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations"
    )
    raw_context: str = Field(
        default="",
        description="Full cleaned text from all scraped pages (grounding data)",
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
