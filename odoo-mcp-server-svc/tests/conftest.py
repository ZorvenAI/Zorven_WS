"""Shared test fixtures for Odoo MCP Server."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_execute_payload() -> dict:
    """Standard execute payload matching orchestrator's ExternalWrapper."""
    return {
        "input_prompt": "Search for sales orders",
        "input_context": {"job_id": "test-job-123"},
        "tenant_context": {"tenant_id": "test-tenant"},
        "config": {"skill_context": "Test skill context"},
        "previous_outputs": {},
    }


@pytest.fixture
def tenant_headers() -> dict:
    """Standard tenant headers."""
    return {"X-Tenant-ID": "test-tenant"}


@pytest.fixture
def service_token_headers() -> dict:
    """Standard service token headers."""
    return {"X-Service-Token": "dev-service-token"}
