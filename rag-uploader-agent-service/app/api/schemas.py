"""
Pydantic v2 request/response models for rag-uploader-agent-svc.

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
    """Request body for POST /v1/execute.

    Matches the payload the orchestrator's ExternalWrapper sends:
    {input_prompt, input_context, tenant_context, config, previous_outputs}
    """

    input_prompt: str = Field(..., description="The user's query or archival request")
    input_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (attachments, chat_history)",
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


class UploadedFileInfo(BaseModel):
    """Details about a file submitted to the ingestion pipeline."""

    file_path: str = Field(default="", description="GCS URI of the file")
    file_name: str = Field(default="", description="Original filename")
    file_type: str = Field(default="", description="MIME type")
    custom_title: str = Field(default="", description="Smart-titled name")
    was_renamed: bool = Field(
        default=False, description="Whether SmartTitler renamed it"
    )
    was_deduplicated: bool = Field(
        default=False, description="Whether this file was skipped as a duplicate"
    )


class ExecuteResponse(BaseModel):
    """Response body for POST /v1/execute.

    Contains archival results. The orchestrator stores this in
    node_outputs["rag_uploader"]. ManagerNode aggregates 'findings'
    and 'recommendations'.
    """

    findings: list[str] = Field(
        default_factory=list, description="Key findings from the archival process"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations"
    )
    uploaded_files: list[UploadedFileInfo] = Field(
        default_factory=list, description="Files submitted to the ingestion pipeline"
    )
    files_skipped_dedup: int = Field(
        default=0, description="Number of files skipped due to deduplication"
    )
    ingestion_events_emitted: int = Field(
        default=0, description="Number of IngestionEvents sent to Kafka"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
