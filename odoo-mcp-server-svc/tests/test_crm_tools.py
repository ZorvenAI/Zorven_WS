"""Tests for CRM domain tools."""

from unittest.mock import AsyncMock

from app.tools.crm.tools import (
    ALL_CRM_TOOLS,
    AssignSalesperson,
    CreateLead,
    GetPipelineStats,
    LogActivity,
    MarkLost,
    MarkWon,
    MergeLeads,
    MoveStage,
    SearchLeads,
    UpdateLead,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestSearchLeads:
    async def test_search_returns_leads(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {"id": 1, "name": "Lead A", "stage_id": [1, "New"]}
        ]
        tool = SearchLeads()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["leads"]) == 1

    async def test_search_no_client(self):
        tool = SearchLeads()
        result = await tool.execute({})
        assert "error" in result


class TestCreateLead:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 42
        tool = CreateLead()
        result = await tool.execute({"name": "New Lead"}, ctx)
        assert result["id"] == 42
        assert result["name"] == "New Lead"


class TestUpdateLead:
    async def test_update_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = UpdateLead()
        result = await tool.execute(
            {"lead_id": 1, "values": {"expected_revenue": 5000}}, ctx
        )
        assert result["success"] is True
        assert result["id"] == 1


class TestMoveStage:
    async def test_move_stage_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = MoveStage()
        result = await tool.execute({"lead_id": 1, "stage_id": 3}, ctx)
        assert result["success"] is True
        assert result["stage_id"] == 3


class TestAssignSalesperson:
    async def test_assign_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = AssignSalesperson()
        result = await tool.execute({"lead_id": 1, "user_id": 5}, ctx)
        assert result["success"] is True
        assert result["user_id"] == 5


class TestLogActivity:
    async def test_log_activity_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [{"id": 99}]
        ctx["rpc_client"].execute_kw.return_value = 10
        tool = LogActivity()
        result = await tool.execute(
            {
                "lead_id": 1,
                "activity_type_id": 2,
                "date_deadline": "2026-04-01",
            },
            ctx,
        )
        assert result["activity_id"] == 10
        assert result["lead_id"] == 1


class TestMarkWon:
    async def test_mark_won_returns_status(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = MarkWon()
        result = await tool.execute({"lead_id": 1}, ctx)
        assert result["status"] == "won"
        assert result["id"] == 1


class TestMarkLost:
    async def test_mark_lost_returns_status(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = MarkLost()
        result = await tool.execute({"lead_id": 1}, ctx)
        assert result["status"] == "lost"
        assert result["id"] == 1


class TestGetPipelineStats:
    async def test_pipeline_stats_returns_stages(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = [
            {
                "stage_id": [1, "New"],
                "stage_id_count": 5,
                "expected_revenue": 25000,
            },
            {
                "stage_id": [2, "Qualified"],
                "stage_id_count": 3,
                "expected_revenue": 15000,
            },
        ]
        tool = GetPipelineStats()
        result = await tool.execute({}, ctx)
        assert result["total_stages"] == 2
        assert len(result["stages"]) == 2


class TestMergeLeads:
    async def test_merge_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = [1]
        tool = MergeLeads()
        result = await tool.execute({"lead_ids": [1, 2, 3]}, ctx)
        assert result["merged_into"] == 1
        assert result["merged_ids"] == [2, 3]

    async def test_merge_too_few_ids(self):
        ctx = _mock_context()
        tool = MergeLeads()
        result = await tool.execute({"lead_ids": [1]}, ctx)
        assert "error" in result


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_create_lead_no_client(self):
        tool = CreateLead()
        result = await tool.execute({"name": "test"})
        assert "error" in result

    async def test_update_lead_no_client(self):
        tool = UpdateLead()
        result = await tool.execute({"lead_id": 1, "values": {}})
        assert "error" in result

    async def test_move_stage_no_client(self):
        tool = MoveStage()
        result = await tool.execute({"lead_id": 1, "stage_id": 1})
        assert "error" in result

    async def test_assign_salesperson_no_client(self):
        tool = AssignSalesperson()
        result = await tool.execute({"lead_id": 1, "user_id": 1})
        assert "error" in result

    async def test_log_activity_no_client(self):
        tool = LogActivity()
        result = await tool.execute(
            {"lead_id": 1, "activity_type_id": 1, "date_deadline": "2026-04-01"}
        )
        assert "error" in result

    async def test_mark_won_no_client(self):
        tool = MarkWon()
        result = await tool.execute({"lead_id": 1})
        assert "error" in result

    async def test_mark_lost_no_client(self):
        tool = MarkLost()
        result = await tool.execute({"lead_id": 1})
        assert "error" in result

    async def test_get_pipeline_stats_no_client(self):
        tool = GetPipelineStats()
        result = await tool.execute({})
        assert "error" in result

    async def test_merge_leads_no_client(self):
        tool = MergeLeads()
        result = await tool.execute({"lead_ids": [1, 2]})
        assert "error" in result


class TestAllCrmTools:
    def test_all_tools_count(self):
        assert len(ALL_CRM_TOOLS) == 10

    def test_all_tools_have_names(self):
        for tool in ALL_CRM_TOOLS:
            assert tool.name != ""
            assert tool.domain == "crm"
