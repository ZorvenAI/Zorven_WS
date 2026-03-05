"""Tests for app/mcp/server.py — create_mcp_server and handler coverage.

Strategy: capture the handler functions registered via @server.list_tools() etc.
by patching the Server class, then invoke them directly for full branch coverage.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.server import SERVER_NAME, SERVER_VERSION, create_mcp_server

# ---------------------------------------------------------------------------
# Metadata constants
# ---------------------------------------------------------------------------


class TestServerMetadata:
    def test_server_name(self):
        assert SERVER_NAME == "odoo-mcp-server"

    def test_server_version(self):
        assert SERVER_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# create_mcp_server — basic construction
# ---------------------------------------------------------------------------


class TestCreateMCPServer:
    def test_returns_server_instance(self):
        server = create_mcp_server()
        assert server is not None

    def test_returns_server_with_none_registries(self):
        server = create_mcp_server(
            tool_registry=None,
            resource_registry=None,
            prompt_registry=None,
        )
        assert server is not None

    def test_returns_server_with_mock_registries(self):
        tool_reg = MagicMock()
        resource_reg = MagicMock()
        prompt_reg = MagicMock()
        server = create_mcp_server(tool_reg, resource_reg, prompt_reg)
        assert server is not None


# ---------------------------------------------------------------------------
# Handler coverage via captured decorators
#
# The mcp SDK Server registers handlers via decorator factories:
#   @server.list_tools()   -> returns decorator -> captures handler fn
# We patch Server so its decorator factories capture the handler functions,
# then call them directly to exercise all branches.
# ---------------------------------------------------------------------------


def _capture_handlers():
    """Call create_mcp_server with a patched Server that captures handlers.

    Returns (handlers_dict, tool_registry, resource_registry, prompt_registry)
    where handlers_dict maps names to the captured async functions.
    """
    handlers = {}

    def _make_capture(name):
        """Return a decorator factory that captures the decorated function."""

        def decorator_factory(*args, **kwargs):
            def decorator(fn):
                handlers[name] = fn
                return fn

            return decorator

        return decorator_factory

    mock_server_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.list_tools = _make_capture("list_tools")
    mock_instance.call_tool = _make_capture("call_tool")
    mock_instance.list_resources = _make_capture("list_resources")
    mock_instance.read_resource = _make_capture("read_resource")
    mock_instance.list_prompts = _make_capture("list_prompts")
    mock_instance.get_prompt = _make_capture("get_prompt")
    mock_server_cls.return_value = mock_instance

    tool_reg = MagicMock()
    resource_reg = MagicMock()
    resource_reg.read = AsyncMock()
    prompt_reg = MagicMock()
    prompt_reg.get_prompt = AsyncMock()

    with patch("app.mcp.server.Server", mock_server_cls):
        create_mcp_server(tool_reg, resource_reg, prompt_reg)

    return handlers, tool_reg, resource_reg, prompt_reg


def _capture_handlers_none():
    """Same as _capture_handlers but with None registries."""
    handlers = {}

    def _make_capture(name):
        def decorator_factory(*args, **kwargs):
            def decorator(fn):
                handlers[name] = fn
                return fn

            return decorator

        return decorator_factory

    mock_server_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.list_tools = _make_capture("list_tools")
    mock_instance.call_tool = _make_capture("call_tool")
    mock_instance.list_resources = _make_capture("list_resources")
    mock_instance.read_resource = _make_capture("read_resource")
    mock_instance.list_prompts = _make_capture("list_prompts")
    mock_instance.get_prompt = _make_capture("get_prompt")
    mock_server_cls.return_value = mock_instance

    with patch("app.mcp.server.Server", mock_server_cls):
        create_mcp_server(None, None, None)

    return handlers


# ---------------------------------------------------------------------------
# list_tools handler
# ---------------------------------------------------------------------------


class TestListToolsHandler:
    async def test_returns_empty_when_registry_none(self):
        handlers = _capture_handlers_none()
        result = await handlers["list_tools"]()
        assert result == []

    async def test_returns_tools_from_registry(self):
        handlers, tool_reg, _, _ = _capture_handlers()
        tool_reg.list_tools.return_value = [
            {
                "name": "odoo_search",
                "description": "Search records",
                "input_schema": {"type": "object"},
            },
            {
                "name": "odoo_create",
                "description": "Create record",
            },
        ]

        result = await handlers["list_tools"]()

        assert len(result) == 2
        assert result[0].name == "odoo_search"
        assert result[0].description == "Search records"
        assert result[1].name == "odoo_create"


# ---------------------------------------------------------------------------
# call_tool handler
# ---------------------------------------------------------------------------


class TestCallToolHandler:
    async def test_returns_not_initialized_when_registry_none(self):
        handlers = _capture_handlers_none()
        result = await handlers["call_tool"]("test_tool", {})
        assert len(result) == 1
        assert "not initialized" in result[0].text.lower()

    async def test_dispatches_to_registry(self):
        handlers, tool_reg, _, _ = _capture_handlers()
        tool_reg.dispatch = AsyncMock(
            return_value={"records": [{"id": 1, "name": "Test"}]}
        )

        result = await handlers["call_tool"]("odoo_search", {"model": "res.partner"})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed["records"][0]["id"] == 1
        tool_reg.dispatch.assert_awaited_once_with(
            "odoo_search", {"model": "res.partner"}
        )

    async def test_returns_error_on_dispatch_exception(self):
        handlers, tool_reg, _, _ = _capture_handlers()
        tool_reg.dispatch = AsyncMock(side_effect=RuntimeError("RPC fail"))

        result = await handlers["call_tool"]("bad_tool", {})

        assert len(result) == 1
        assert "Error:" in result[0].text
        assert "RPC fail" in result[0].text


# ---------------------------------------------------------------------------
# list_resources handler
# ---------------------------------------------------------------------------


class TestListResourcesHandler:
    async def test_returns_empty_when_registry_none(self):
        handlers = _capture_handlers_none()
        result = await handlers["list_resources"]()
        assert result == []

    async def test_returns_resources_from_registry(self):
        handlers, _, resource_reg, _ = _capture_handlers()
        resource_reg.list_resources.return_value = [
            MagicMock(uri="odoo://schema/res.partner")
        ]

        result = await handlers["list_resources"]()

        assert len(result) == 1


# ---------------------------------------------------------------------------
# read_resource handler
# ---------------------------------------------------------------------------


class TestReadResourceHandler:
    async def test_returns_not_initialized_when_registry_none(self):
        handlers = _capture_handlers_none()
        result = await handlers["read_resource"]("odoo://x")
        assert "not initialized" in result.lower()

    async def test_reads_from_registry(self):
        handlers, _, resource_reg, _ = _capture_handlers()
        resource_reg.read = AsyncMock(return_value="schema content here")

        result = await handlers["read_resource"]("odoo://schema/res.partner")

        assert result == "schema content here"
        resource_reg.read.assert_awaited_once_with("odoo://schema/res.partner")


# ---------------------------------------------------------------------------
# list_prompts handler
# ---------------------------------------------------------------------------


class TestListPromptsHandler:
    async def test_returns_empty_when_registry_none(self):
        handlers = _capture_handlers_none()
        result = await handlers["list_prompts"]()
        assert result == []

    async def test_returns_prompts_from_registry(self):
        handlers, _, _, prompt_reg = _capture_handlers()
        prompt_reg.list_prompts.return_value = [MagicMock(name="crm-help")]

        result = await handlers["list_prompts"]()

        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_prompt handler
# ---------------------------------------------------------------------------


class TestGetPromptHandler:
    async def test_returns_empty_result_when_registry_none(self):
        handlers = _capture_handlers_none()
        result = await handlers["get_prompt"]("any-prompt", None)

        assert result.description == "Not available"
        assert result.messages == []

    async def test_delegates_to_registry(self):
        handlers, _, _, prompt_reg = _capture_handlers()
        expected = MagicMock()
        prompt_reg.get_prompt = AsyncMock(return_value=expected)

        result = await handlers["get_prompt"]("crm-help", {"arg": "val"})

        assert result is expected
        prompt_reg.get_prompt.assert_awaited_once_with("crm-help", {"arg": "val"})
