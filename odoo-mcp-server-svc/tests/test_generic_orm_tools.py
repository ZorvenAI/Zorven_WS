"""Tests for generic ORM tools."""

from unittest.mock import AsyncMock

from app.tools.generic.orm_tools import (
    ALL_GENERIC_TOOLS,
    OdooCreateTool,
    OdooDeleteTool,
    OdooGetFieldsTool,
    OdooReadTool,
    OdooSearchReadTool,
    OdooSearchTool,
    OdooWriteTool,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestOdooSearchTool:
    async def test_search_returns_ids(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = [1, 2, 3]
        tool = OdooSearchTool()
        result = await tool.execute({"model": "res.partner"}, ctx)
        assert result["ids"] == [1, 2, 3]
        assert result["count"] == 3

    async def test_search_no_client(self):
        tool = OdooSearchTool()
        result = await tool.execute({"model": "res.partner"})
        assert "error" in result


class TestOdooReadTool:
    async def test_read_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = [{"id": 1, "name": "Test"}]
        tool = OdooReadTool()
        result = await tool.execute({"model": "res.partner", "ids": [1]}, ctx)
        assert len(result["records"]) == 1


class TestOdooCreateTool:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 42
        tool = OdooCreateTool()
        result = await tool.execute(
            {"model": "res.partner", "values": {"name": "New"}}, ctx
        )
        assert result["id"] == 42


class TestOdooWriteTool:
    async def test_write_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = OdooWriteTool()
        result = await tool.execute(
            {"model": "res.partner", "ids": [1], "values": {"name": "Updated"}},
            ctx,
        )
        assert result["success"] is True


class TestOdooDeleteTool:
    async def test_delete_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].unlink.return_value = True
        tool = OdooDeleteTool()
        result = await tool.execute({"model": "res.partner", "ids": [1]}, ctx)
        assert result["deleted"] is True


class TestOdooSearchReadTool:
    async def test_search_read_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [{"id": 1, "name": "Test"}]
        tool = OdooSearchReadTool()
        result = await tool.execute({"model": "res.partner"}, ctx)
        assert result["count"] == 1


class TestOdooGetFieldsTool:
    async def test_get_fields_returns_schema(self):
        ctx = _mock_context()
        ctx["rpc_client"].fields_get.return_value = {
            "name": {"type": "char", "string": "Name"}
        }
        tool = OdooGetFieldsTool()
        result = await tool.execute({"model": "res.partner"}, ctx)
        assert "name" in result["fields"]


class TestAllGenericTools:
    def test_all_tools_count(self):
        assert len(ALL_GENERIC_TOOLS) == 8

    def test_all_tools_have_names(self):
        for tool in ALL_GENERIC_TOOLS:
            assert tool.name != ""
            assert tool.domain == "generic"
