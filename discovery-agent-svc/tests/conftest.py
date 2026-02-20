"""Shared test fixtures for discovery-agent-svc."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_execute_payload() -> dict[str, Any]:
    """
    A valid ExecuteRequest payload matching what the orchestrator's
    ExternalWrapper sends to external agent services.
    """
    return {
        "input_prompt": "Analyze brand positioning for Acme Corp",
        "input_context": {"company_id": 42},
        "tenant_context": {
            "tenant_id": "1",
            "gcs_raw_bucket": "brand-automator/1/",
            "gcs_processed_bucket": "brand-automator-curated/1/",
            "rag_data_store_id": "ds-123",
        },
        "config": {"focus": "market_trends,competitors"},
        "previous_outputs": {},
    }


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    """Headers with X-Tenant-ID for authenticated requests."""
    return {"X-Tenant-ID": "test-tenant"}
