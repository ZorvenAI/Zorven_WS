"""
Pydantic v2 request/response models for the orchestrator API.

These schemas match the service contracts defined in the Django
OrchestratorDispatcher (ai-brand-automator/orchestration/services.py).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ManifestNode(BaseModel):
    """A single node in the pipeline manifest."""

    id: str
    type: Literal["internal", "external"]
    handler: Optional[str] = None
    url: Optional[str] = None
    config: dict = Field(default_factory=dict)


class ManifestData(BaseModel):
    """
    HLD v6.0 Pipeline-as-Code manifest structure.

    Matches the manifest_data JSONField on PipelineManifest model.
    """

    nodes: list[ManifestNode]
    edges: list[list[str]]
    global_config: dict = Field(default_factory=dict)


class TenantContext(BaseModel):
    """Tenant-scoped context for secure data isolation."""

    tenant_id: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""


class AvailableManifest(BaseModel):
    """Manifest entry for intent routing, optionally includes full manifest_data."""

    pipeline_id: str
    name: str
    description: str = ""
    manifest_data: Optional[dict] = None


class DispatchRequest(BaseModel):
    """
    Job dispatch payload from core-api-service.

    Matches the payload built by OrchestratorDispatcher._build_payload().
    """

    job_id: str
    manifest: Optional[ManifestData] = None
    input_prompt: str
    input_context: dict = Field(default_factory=dict)
    tenant_context: TenantContext = Field(default_factory=TenantContext)
    callback_url: str
    available_manifests: Optional[list[AvailableManifest]] = None


class DispatchResponse(BaseModel):
    """Response confirming job acceptance."""

    status: str = "accepted"


class CancelResponse(BaseModel):
    """Response confirming job cancellation."""

    status: str = "cancelled"


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
