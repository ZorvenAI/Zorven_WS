"""Tests for Project domain tools."""

from unittest.mock import AsyncMock

from app.tools.project.tools import (
    ALL_PROJECT_TOOLS,
    CreateTask,
    GetProfitability,
    LogTimesheet,
    UpdateTask,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCreateTask:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 42
        tool = CreateTask()
        result = await tool.execute({"name": "Implement feature", "project_id": 1}, ctx)
        assert result["id"] == 42
        assert result["model"] == "project.task"

    async def test_create_no_client(self):
        tool = CreateTask()
        result = await tool.execute({"name": "Implement feature", "project_id": 1})
        assert "error" in result


class TestUpdateTask:
    async def test_update_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = UpdateTask()
        result = await tool.execute({"task_id": 42, "values": {"stage_id": 4}}, ctx)
        assert result["success"] is True
        assert result["id"] == 42
        assert result["model"] == "project.task"


class TestLogTimesheet:
    async def test_log_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 100
        tool = LogTimesheet()
        result = await tool.execute(
            {
                "task_id": 42,
                "project_id": 1,
                "unit_amount": 2.5,
            },
            ctx,
        )
        assert result["id"] == 100
        assert result["model"] == "account.analytic.line"


class TestGetProfitability:
    async def test_profitability_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "Project Alpha",
                "budget": 50000,
                "total_timesheet_time": 120.5,
            }
        ]
        tool = GetProfitability()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert result["model"] == "project.project"
        assert len(result["records"]) == 1


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_update_task_no_client(self):
        tool = UpdateTask()
        result = await tool.execute({"task_id": 1, "values": {}})
        assert "error" in result

    async def test_log_timesheet_no_client(self):
        tool = LogTimesheet()
        result = await tool.execute({"task_id": 1, "project_id": 1, "unit_amount": 1.0})
        assert "error" in result

    async def test_get_profitability_no_client(self):
        tool = GetProfitability()
        result = await tool.execute({})
        assert "error" in result


class TestAllProjectTools:
    def test_all_tools_count(self):
        assert len(ALL_PROJECT_TOOLS) == 4

    def test_all_tools_have_names(self):
        for tool in ALL_PROJECT_TOOLS:
            assert tool.name != ""
            assert tool.domain == "project"
