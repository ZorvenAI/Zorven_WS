"""Tests for tool registry."""

from unittest.mock import AsyncMock

from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry
from app.tools.generic.orm_tools import ALL_GENERIC_TOOLS


class _FakeFailTool(BaseTool):
    name = "fail_tool"
    description = "A tool that always raises"
    domain = "test"
    required_operation = "read"
    input_schema = {"type": "object", "properties": {}}

    async def execute(self, arguments, context=None):
        raise RuntimeError("Tool exploded")


class TestToolRegistry:
    def test_register_tool(self):
        registry = ToolRegistry()
        tool = ALL_GENERIC_TOOLS[0]
        registry.register(tool)
        assert registry.count == 1

    def test_register_duplicate_overwrites(self):
        registry = ToolRegistry()
        tool = ALL_GENERIC_TOOLS[0]
        registry.register(tool)
        registry.register(tool)
        assert registry.count == 1

    def test_get_tool_by_name(self):
        registry = ToolRegistry()
        tool = ALL_GENERIC_TOOLS[0]
        registry.register(tool)
        found = registry.get_tool(tool.name)
        assert found is tool

    def test_get_unknown_tool_returns_none(self):
        registry = ToolRegistry()
        assert registry.get_tool("nonexistent") is None

    def test_list_tools_returns_all(self):
        registry = ToolRegistry()
        for tool in ALL_GENERIC_TOOLS:
            registry.register(tool)
        tools = registry.list_tools()
        assert len(tools) == 8

    def test_list_tools_by_domain(self):
        registry = ToolRegistry()
        for tool in ALL_GENERIC_TOOLS:
            registry.register(tool)
        generic_tools = registry.list_tools(domain="generic")
        assert len(generic_tools) == 8

    def test_list_tools_unknown_domain(self):
        registry = ToolRegistry()
        for tool in ALL_GENERIC_TOOLS:
            registry.register(tool)
        assert registry.list_tools(domain="nonexistent") == []

    def test_list_domains(self):
        registry = ToolRegistry()
        for tool in ALL_GENERIC_TOOLS:
            registry.register(tool)
        domains = registry.list_domains()
        assert "generic" in domains

    async def test_dispatch_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.dispatch("unknown", {})
        assert "error" in result

    async def test_dispatch_calls_tool(self):
        registry = ToolRegistry()
        for tool in ALL_GENERIC_TOOLS:
            registry.register(tool)
        result = await registry.dispatch("odoo_search", {"model": "res.partner"})
        # No RPC client in context, should return error
        assert "error" in result

    async def test_dispatch_tool_exception_returns_error(self):
        registry = ToolRegistry()
        registry.register(_FakeFailTool())
        result = await registry.dispatch("fail_tool", {})
        assert "error" in result
        assert "Tool exploded" in result["error"]
