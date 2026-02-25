"""
Pydantic v2 request/response models for content-agent-svc.

The ExecuteRequest matches the payload sent by the orchestrator's
ExternalWrapper (pipeline-orchestrator-svc/app/nodes/external_wrapper.py).
"""

from typing import Any

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

    input_prompt: str = Field(..., description="The user's query or blog request")
    input_context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context from the user"
    )
    tenant_context: TenantContext | dict[str, Any] = Field(
        default_factory=dict,
        description="Tenant isolation data (GCS buckets, RAG store)",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Node-level config merged with global_config",
    )
    previous_outputs: dict[str, Any] = Field(
        default_factory=dict, description="Outputs from upstream pipeline nodes"
    )


class SEOMeta(BaseModel):
    """SEO metadata for the generated blog post."""

    title: str = Field(default="", description="Meta title (<=60 chars)")
    description: str = Field(default="", description="Meta description (<=160 chars)")
    keywords: list[str] = Field(
        default_factory=list, description="Target SEO keywords"
    )
    slug: str = Field(default="", description="URL-friendly slug")


class FAQItem(BaseModel):
    """A single FAQ item for AEO schema."""

    question: str = Field(default="", description="FAQ question")
    answer: str = Field(default="", description="FAQ answer")


class AEOSchema(BaseModel):
    """Answer Engine Optimization schema data."""

    faq_items: list[FAQItem] = Field(
        default_factory=list, description="FAQ items for structured data"
    )
    structured_data: dict[str, Any] = Field(
        default_factory=dict, description="JSON-LD structured data"
    )


class Citation(BaseModel):
    """A citation linking a claim to its source."""

    claim: str = Field(default="", description="The claim being cited")
    source_title: str = Field(default="", description="Title of the source")
    source_url: str = Field(default="", description="URL of the source")


class ExecuteResponse(BaseModel):
    """
    Response body for POST /v1/execute.

    Contains the generated blog post with SEO/AEO/GEO metadata.
    The orchestrator stores this in node_outputs[node_id].
    ManagerNode aggregates 'findings' and 'recommendations'.
    """

    findings: list[str] = Field(
        default_factory=list, description="Key findings from the blog authoring process"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations"
    )
    blog_content: str = Field(
        default="", description="Full Markdown blog post"
    )
    seo_meta: SEOMeta | None = Field(
        default=None, description="SEO metadata"
    )
    aeo_schema: AEOSchema | None = Field(
        default=None, description="AEO structured data"
    )
    citations: list[Citation] = Field(
        default_factory=list, description="Source citations"
    )
    gcs_uri: str = Field(
        default="", description="GCS URI where blog was saved"
    )
    word_count: int = Field(
        default=0, description="Word count of the blog content"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
