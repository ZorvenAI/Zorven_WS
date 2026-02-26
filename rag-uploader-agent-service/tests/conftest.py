"""Shared test fixtures for rag-uploader-agent-service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.schemas import ExecuteRequest


@pytest.fixture
def sample_attachments() -> list[dict[str, Any]]:
    """Sample attachment data from input_context."""
    return [
        {
            "id": 1,
            "asset_id": 101,
            "file_name": "report.pdf",
            "file_type": "application/pdf",
            "gcs_bucket": "brand-automator",
            "gcs_path": "_landing/1/abc_report.pdf",
        },
        {
            "id": 2,
            "asset_id": 102,
            "file_name": "upload.pdf",
            "file_type": "application/pdf",
            "gcs_bucket": "brand-automator",
            "gcs_path": "_landing/2/upload.pdf",
        },
    ]


@pytest.fixture
def sample_previous_outputs() -> dict[str, Any]:
    """Sample previous_outputs with a blog_author GCS URI."""
    return {
        "blog_author": {
            "findings": ["Blog written successfully"],
            "blog_content": "# My Blog Post\n\nContent here...",
            "gcs_uri": "gs://brand-automator/tenant-1/content/blogs/2026/02/my-blog.md",
            "word_count": 500,
        },
        "web_research": {
            "findings": ["Found relevant data"],
        },
    }


@pytest.fixture
def sample_execute_request(
    sample_attachments: list[dict[str, Any]],
    sample_previous_outputs: dict[str, Any],
) -> ExecuteRequest:
    """A complete ExecuteRequest with attachments and previous outputs."""
    return ExecuteRequest(
        input_prompt="Save these documents to my knowledge base",
        input_context={
            "job_id": "test-job-123",
            "attachments": sample_attachments,
            "chat_history": [
                {"role": "user", "content": "Save these documents"},
            ],
        },
        tenant_context={"tenant_id": "test-tenant"},
        config={},
        previous_outputs=sample_previous_outputs,
    )


@pytest.fixture
def mock_redis_manager() -> AsyncMock:
    """Mock RedisManager that allows all operations."""
    manager = AsyncMock()
    manager.check_rate_limit.return_value = True
    manager.check_dedup.return_value = False
    manager.mark_ingested.return_value = None
    manager.close.return_value = None
    manager.hash_uri = MagicMock(side_effect=lambda uri: f"hash_{uri}")
    return manager


@pytest.fixture
def sample_stub_previous_outputs() -> dict[str, Any]:
    """Sample previous_outputs where blog_author has a stub GCS URI."""
    return {
        "blog_author": {
            "findings": ["Blog written successfully"],
            "blog_content": "# My Blog Post\n\nContent here...",
            "gcs_uri": "stub://no-gcs/tenant-1/content/blogs/my-blog.md",
            "seo_meta": {"slug": "my-blog-post"},
            "word_count": 500,
        },
        "web_research": {
            "findings": ["Found relevant data"],
        },
    }


@pytest.fixture
def mock_trace_producer() -> AsyncMock:
    """Mock TraceProducer."""
    producer = AsyncMock()
    producer.send_step.return_value = None
    producer.stop.return_value = None
    return producer
