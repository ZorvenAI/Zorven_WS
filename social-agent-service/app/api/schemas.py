"""Pydantic v2 request and response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    tenant_id: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""


class ExecuteRequest(BaseModel):
    input_prompt: str
    input_context: dict[str, Any] = Field(default_factory=dict)
    tenant_context: TenantContext | dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


class SocialPost(BaseModel):
    platform: str = Field(default="", description="Target platform")
    content: str = Field(default="", description="Platform-specific post content")
    hashtags: list[str] = Field(default_factory=list)
    char_count: int = Field(default=0)
    post_type: str = Field(default="status", description="e.g. article_share, thread")


class PublishResult(BaseModel):
    platform: str = Field(default="")
    status: str = Field(
        default="pending", description="published, scheduled, draft, failed"
    )
    post_id: str | None = Field(default=None)
    post_url: str | None = Field(default=None)
    scheduled_date: str | None = Field(default=None)
    error: str | None = Field(default=None)


class ExecuteResponse(BaseModel):
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    adapted_posts: list[SocialPost] = Field(default_factory=list)
    publish_results: list[PublishResult] = Field(default_factory=list)
    draft_stored: bool = Field(default=False)
    platforms_posted: list[str] = Field(default_factory=list)
    action_type: str = Field(
        default="publish_now", description="publish_now or schedule"
    )


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
