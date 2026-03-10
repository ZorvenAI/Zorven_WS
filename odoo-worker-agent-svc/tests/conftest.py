"""Shared test fixtures for odoo-worker-agent-svc."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

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
    """A valid ExecuteRequest payload matching the orchestrator contract."""
    return {
        "input_prompt": "Create a sales order for customer ABC with 10 units of Widget Pro",
        "input_context": {"company_id": 42, "job_id": "job-123"},
        "tenant_context": {
            "tenant_id": "1",
            "user_roles": ["sales_manager", "sales_user"],
            "rag_data_store_id": "",
        },
        "config": {"skill_context": ""},
        "previous_outputs": {},
    }


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    """Headers with X-Tenant-ID and X-Service-Token for authenticated requests."""
    return {"X-Tenant-ID": "test-tenant", "X-Service-Token": "dev-service-token"}


@pytest.fixture
def service_token_headers() -> dict[str, str]:
    """Headers with only X-Service-Token (no tenant)."""
    return {"X-Service-Token": "dev-service-token"}


@pytest.fixture
def mock_gemini_client() -> MagicMock:
    """Mock GeminiClient for unit tests."""
    client = MagicMock()
    client.plan = AsyncMock()
    client.reflect = AsyncMock()
    client.classify_persona = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_mcp_client() -> MagicMock:
    """Mock MCPClient for unit tests."""
    client = MagicMock()
    client.call_tool = AsyncMock()
    client.list_tools = AsyncMock(return_value=[])
    client.health_check = AsyncMock(return_value=True)
    client.close = AsyncMock()
    return client


@pytest.fixture
def sample_persona_data() -> dict[str, Any]:
    """Sample persona definition for testing."""
    return {
        "name": "sales_manager",
        "display_name": "Sales Manager",
        "description": "Manages sales operations",
        "domains": ["crm", "sales"],
        "responsibilities": ["Create sales orders", "Manage leads"],
        "required_roles": ["sales_manager"],
        "preferred_tools": ["odoo_search", "sales_create_order"],
        "system_prompt": "You are a Sales Manager.",
        "triggers": ["sales order", "quotation", "lead"],
        "priority": 8,
    }
