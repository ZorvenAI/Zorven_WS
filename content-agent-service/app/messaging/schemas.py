"""
Pydantic models for Kafka event payloads.

TraceEvent           — step updates for ThoughtTrace UI
ContentPublishedEvent — blog published notification for downstream agents
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """Trace event sent to agent-trace-topic."""

    job_id: str = ""
    node_id: str = "content_worker"
    status: str = "PROCESSING"
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class ContentPublishedEvent(BaseModel):
    """Event emitted when a blog is published to GCS."""

    blog_id: str = ""
    tenant_id: str = ""
    title: str = ""
    markdown_uri: str = ""
    seo_meta: dict[str, Any] = Field(default_factory=dict)
    published_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
