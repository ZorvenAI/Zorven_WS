"""Tests for app/mcp/transport.py — Streamable HTTP transport.

Covers the POST /mcp endpoint and _dispatch_mcp_method dispatcher.
Does NOT test the SSE endpoint (infinite loop).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.transport import _dispatch_mcp_method

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_tool():
    """Return a MagicMock that has .model_dump()."""
    t = MagicMock()
    t.model_dump.return_value = {
        "name": "odoo_search",
        "description": "Search Odoo records",
        "inputSchema": {},
    }
    return t


def _mock_content():
    """Return a MagicMock resembling a TextContent with .model_dump()."""
    c = MagicMock()
    c.model_dump.return_value = {"type": "text", "text": "result data"}
    return c


def _mock_resource():
    r = MagicMock()
    r.model_dump.return_value = {"uri": "odoo://schema/res.partner", "name": "Schema"}
    return r


def _mock_prompt():
    p = MagicMock()
    p.model_dump.return_value = {"name": "crm-help", "description": "CRM helper"}
    return p


def _mock_prompt_result():
    pr = MagicMock()
    pr.model_dump.return_value = {
        "description": "CRM helper",
        "messages": [{"role": "user", "content": {"type": "text", "text": "Help"}}],
    }
    return pr


# ---------------------------------------------------------------------------
# POST /mcp — HTTP endpoint tests (use conftest client)
# ---------------------------------------------------------------------------


class TestMCPPostEndpoint:
    async def test_returns_503_when_server_is_none(self, client):
        """Default state: mcp_server is None -> 503."""
        with patch("app.mcp.transport.mcp_server", None):
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
            )
        assert response.status_code == 503
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["error"]["code"] == -32603
        assert "not initialized" in data["error"]["message"]
        assert data["id"] is None

    async def test_returns_200_with_result(self, client):
        """When mcp_server is set and dispatch succeeds, return 200."""
        mock_server = AsyncMock()
        mock_server.list_tools = AsyncMock(return_value=[_mock_tool()])

        with patch("app.mcp.transport.mcp_server", mock_server):
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 42,
                    "method": "tools/list",
                    "params": {},
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 42
        assert "tools" in data["result"]
        assert len(data["result"]["tools"]) == 1

    async def test_returns_500_on_dispatch_exception(self, client):
        """Exception in _dispatch_mcp_method -> 500 JSON-RPC error."""
        mock_server = AsyncMock()
        mock_server.list_tools = AsyncMock(side_effect=RuntimeError("kaboom"))

        with patch("app.mcp.transport.mcp_server", mock_server):
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "tools/list",
                    "params": {},
                },
            )
        assert response.status_code == 500
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["error"]["code"] == -32603
        assert "kaboom" in data["error"]["message"]

    async def test_preserves_request_id(self, client):
        """Successful response carries the original request id."""
        mock_server = AsyncMock()
        mock_server.list_tools = AsyncMock(return_value=[])

        with patch("app.mcp.transport.mcp_server", mock_server):
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "abc-123",
                    "method": "tools/list",
                    "params": {},
                },
            )
        data = response.json()
        assert data["id"] == "abc-123"


# ---------------------------------------------------------------------------
# _dispatch_mcp_method — unit tests
# ---------------------------------------------------------------------------


class TestDispatchMCPMethod:
    @patch("app.mcp.transport.mcp_server")
    async def test_tools_list(self, mock_server):
        tool = _mock_tool()
        mock_server.list_tools = AsyncMock(return_value=[tool])

        result = await _dispatch_mcp_method("tools/list", {})

        assert "tools" in result
        assert len(result["tools"]) == 1
        tool.model_dump.assert_called_once()

    @patch("app.mcp.transport.mcp_server")
    async def test_tools_call(self, mock_server):
        content = _mock_content()
        mock_server.call_tool = AsyncMock(return_value=[content])

        result = await _dispatch_mcp_method(
            "tools/call",
            {"name": "odoo_search", "arguments": {"model": "res.partner"}},
        )

        assert "content" in result
        assert len(result["content"]) == 1
        mock_server.call_tool.assert_awaited_once_with(
            "odoo_search", {"model": "res.partner"}
        )

    @patch("app.mcp.transport.mcp_server")
    async def test_resources_list(self, mock_server):
        resource = _mock_resource()
        mock_server.list_resources = AsyncMock(return_value=[resource])

        result = await _dispatch_mcp_method("resources/list", {})

        assert "resources" in result
        assert len(result["resources"]) == 1

    @patch("app.mcp.transport.mcp_server")
    async def test_resources_read(self, mock_server):
        mock_server.read_resource = AsyncMock(return_value="schema content")

        result = await _dispatch_mcp_method(
            "resources/read", {"uri": "odoo://schema/res.partner"}
        )

        assert result["contents"][0]["uri"] == "odoo://schema/res.partner"
        assert result["contents"][0]["text"] == "schema content"

    @patch("app.mcp.transport.mcp_server")
    async def test_prompts_list(self, mock_server):
        prompt = _mock_prompt()
        mock_server.list_prompts = AsyncMock(return_value=[prompt])

        result = await _dispatch_mcp_method("prompts/list", {})

        assert "prompts" in result
        assert len(result["prompts"]) == 1

    @patch("app.mcp.transport.mcp_server")
    async def test_prompts_get(self, mock_server):
        prompt_result = _mock_prompt_result()
        mock_server.get_prompt = AsyncMock(return_value=prompt_result)

        result = await _dispatch_mcp_method(
            "prompts/get", {"name": "crm-help", "arguments": None}
        )

        assert "description" in result
        mock_server.get_prompt.assert_awaited_once_with("crm-help", None)

    @patch("app.mcp.transport.mcp_server")
    async def test_initialize(self, mock_server):
        result = await _dispatch_mcp_method("initialize", {})

        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "odoo-mcp-server"
        assert result["serverInfo"]["version"] == "1.0.0"
        assert "capabilities" in result

    @patch("app.mcp.transport.mcp_server")
    async def test_unknown_method_raises_value_error(self, mock_server):
        with pytest.raises(ValueError, match="Unknown MCP method"):
            await _dispatch_mcp_method("nonexistent/method", {})

    @patch("app.mcp.transport.mcp_server")
    async def test_tools_call_default_params(self, mock_server):
        """tools/call uses empty defaults when name/arguments missing."""
        content = _mock_content()
        mock_server.call_tool = AsyncMock(return_value=[content])

        result = await _dispatch_mcp_method("tools/call", {})

        mock_server.call_tool.assert_awaited_once_with("", {})

    @patch("app.mcp.transport.mcp_server")
    async def test_resources_read_default_uri(self, mock_server):
        """resources/read uses empty string when uri missing."""
        mock_server.read_resource = AsyncMock(return_value="")

        result = await _dispatch_mcp_method("resources/read", {})

        mock_server.read_resource.assert_awaited_once_with("")

    @patch("app.mcp.transport.mcp_server")
    async def test_prompts_get_default_name(self, mock_server):
        """prompts/get uses empty string for name, None for arguments."""
        prompt_result = _mock_prompt_result()
        mock_server.get_prompt = AsyncMock(return_value=prompt_result)

        result = await _dispatch_mcp_method("prompts/get", {})

        mock_server.get_prompt.assert_awaited_once_with("", None)

    @patch("app.mcp.transport.mcp_server")
    async def test_initialize_capabilities_structure(self, mock_server):
        result = await _dispatch_mcp_method("initialize", {})

        caps = result["capabilities"]
        assert caps["tools"]["listChanged"] is False
        assert caps["resources"]["subscribe"] is False
        assert caps["resources"]["listChanged"] is False
        assert caps["prompts"]["listChanged"] is False
