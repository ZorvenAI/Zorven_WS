"""Kafka message schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    job_id: str = ""
    node_id: str = "social_promoter"
    status: str = "PROCESSING"
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class SocialAuditEvent(BaseModel):
    tenant_id: str = ""
    job_id: str = ""
    platform: str = ""
    action: str = ""
    content_preview: str = ""
    user_role: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ContentPublishedEvent(BaseModel):
    blog_id: str = ""
    tenant_id: str = ""
    title: str = ""
    markdown_uri: str = ""
    seo_meta: dict[str, Any] = Field(default_factory=dict)
    published_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
