"""Builds metadata dicts for IngestionEvent payloads."""

from datetime import datetime, timezone
from typing import Any, Optional


def generate(
    file_name: str,
    custom_title: str,
    source: str,
    job_id: str,
    tenant_id: str,
    additional: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build metadata dict for an ingestion event.

    Args:
        file_name: Original filename.
        custom_title: Smart-titled name (may equal file_name if not renamed).
        source: Where the file came from (e.g., "attachment", "blog_author").
        job_id: Pipeline job ID.
        tenant_id: Tenant identifier.
        additional: Extra metadata to merge in.

    Returns:
        Metadata dict suitable for IngestionEvent.metadata field.
    """
    # Apply additional fields first so required fields cannot be overwritten
    meta: dict[str, Any] = {}
    if additional:
        meta.update(additional)

    # Required fields always take precedence
    meta.update(
        {
            "original_name": file_name,
            "custom_title": custom_title,
            "source_agent": "rag-uploader-agent-service",
            "source_node": source,
            "job_id": job_id,
            "tenant_id": tenant_id,
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return meta
