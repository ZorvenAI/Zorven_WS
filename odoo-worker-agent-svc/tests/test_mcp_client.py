"""Tests for MCP client."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.circuit_breaker import CircuitBreaker, CircuitState
from app.services.mcp_client import MCPClient, ToolCallResponse


@pytest.fixture
def mcp_client():
    return MCPClient(
        base_url="http://localhost:8095",
        timeout=5.0,
    )


async def test_call_tool_success(mcp_client):
    """Should return success response on 200."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "ok"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mcp_client._client = mock_client

    result = await mcp_client.call_tool(
        tool_name="odoo_search",
        arguments={"model": "res.partner"},
        tenant_id="test-tenant",
    )
    assert result.success is True
    assert result.data == {"result": "ok"}
    assert result.tool_name == "odoo_search"


async def test_call_tool_timeout(mcp_client):
    """Should return failure on timeout."""
    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mcp_client._client = mock_client

    result = await mcp_client.call_tool(
        tool_name="odoo_search",
        arguments={},
        tenant_id="test-tenant",
    )
    assert result.success is False
    assert "Timeout" in result.error


async def test_call_tool_circuit_breaker_open():
    """Should reject calls when circuit breaker is open."""
    cb = CircuitBreaker(failure_threshold=1)
    cb.record_failure()  # Trip the breaker
    assert cb.is_open

    client = MCPClient(
        base_url="http://localhost:8095",
        circuit_breaker=cb,
    )

    result = await client.call_tool("odoo_search", {}, "test")
    assert result.success is False
    assert "Circuit breaker" in result.error


async def test_health_check_success(mcp_client):
    """Should return True on healthy MCP server."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mcp_client._client = mock_client

    assert await mcp_client.health_check() is True


async def test_health_check_failure(mcp_client):
    """Should return False on unhealthy MCP server."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
    mcp_client._client = mock_client

    assert await mcp_client.health_check() is False


async def test_list_tools(mcp_client):
    """Should return tool list from MCP server."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tools": [{"name": "odoo_search"}, {"name": "odoo_read"}]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mcp_client._client = mock_client

    tools = await mcp_client.list_tools("test-tenant")
    assert len(tools) == 2


async def test_tool_call_response_to_dict():
    """ToolCallResponse should serialize to dict."""
    resp = ToolCallResponse(
        success=True,
        data={"key": "value"},
        tool_name="test_tool",
    )
    d = resp.to_dict()
    assert d["success"] is True
    assert d["tool_name"] == "test_tool"
