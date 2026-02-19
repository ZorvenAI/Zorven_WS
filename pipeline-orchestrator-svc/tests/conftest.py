"""Shared test fixtures for pipeline-orchestrator-svc."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_dispatch_payload():
    """Sample dispatch request matching the Django OrchestratorDispatcher."""
    return {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "manifest": {
            "nodes": [
                {
                    "id": "intent_router",
                    "type": "internal",
                    "handler": "RouterNode",
                },
                {
                    "id": "web_research",
                    "type": "external",
                    "url": "http://discovery-agent-svc/v1/search",
                    "config": {"focus": "market_trends"},
                },
            ],
            "edges": [["intent_router", "web_research"]],
            "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7},
        },
        "input_prompt": "Analyze brand positioning for Acme Corp",
        "input_context": {"company_id": 42},
        "tenant_context": {
            "tenant_id": "1",
            "gcs_raw_bucket": "brand-automator/1/",
            "gcs_processed_bucket": "brand-automator-curated/1/",
            "rag_data_store_id": "ds-123",
        },
        "callback_url": "http://backend:8001/api/v1/orchestration/jobs/550e8400-e29b-41d4-a716-446655440000/callback/",
    }


@pytest.fixture
def service_token_headers():
    """Headers with valid service token."""
    return {
        "X-Service-Token": "dev-service-token",
        "Content-Type": "application/json",
    }
