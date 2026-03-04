"""Tests for Manufacturing domain tools."""

from unittest.mock import AsyncMock

from app.tools.manufacturing.tools import (
    ALL_MANUFACTURING_TOOLS,
    CompleteProduction,
    CreateBOM,
    CreateProduction,
    GetCapacity,
    PlanSchedule,
    QualityCheck,
    SearchManufacturingOrders,
    StartProduction,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCreateBOM:
    async def test_create_bom_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 10
        tool = CreateBOM()
        result = await tool.execute(
            {
                "product_tmpl_id": 1,
                "bom_line_ids": [
                    {"product_id": 2, "product_qty": 3},
                    {"product_id": 3, "product_qty": 1},
                ],
            },
            ctx,
        )
        assert result["bom_id"] == 10
        assert result["success"] is True

    async def test_create_bom_no_client(self):
        tool = CreateBOM()
        result = await tool.execute(
            {
                "product_tmpl_id": 1,
                "bom_line_ids": [{"product_id": 2, "product_qty": 3}],
            }
        )
        assert "error" in result


class TestCreateProduction:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 20
        tool = CreateProduction()
        result = await tool.execute(
            {"product_id": 1, "product_qty": 10, "bom_id": 10}, ctx
        )
        assert result["production_id"] == 20
        assert result["success"] is True


class TestStartProduction:
    async def test_start_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.side_effect = [True, True]
        tool = StartProduction()
        result = await tool.execute({"production_id": 20}, ctx)
        assert result["started"] is True
        assert result["production_id"] == 20


class TestCompleteProduction:
    async def test_complete_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = CompleteProduction()
        result = await tool.execute({"production_id": 20}, ctx)
        assert result["completed"] is True
        assert result["production_id"] == 20


class TestPlanSchedule:
    async def test_plan_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "MO/001",
                "product_id": [1, "Widget"],
                "state": "confirmed",
            }
        ]
        tool = PlanSchedule()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestQualityCheck:
    async def test_quality_pass(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        ctx["rpc_client"].execute_kw.return_value = True
        tool = QualityCheck()
        result = await tool.execute({"check_id": 5, "quality_state": "pass"}, ctx)
        assert result["recorded"] is True
        assert result["quality_state"] == "pass"

    async def test_quality_fail(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        ctx["rpc_client"].execute_kw.return_value = True
        tool = QualityCheck()
        result = await tool.execute({"check_id": 5, "quality_state": "fail"}, ctx)
        assert result["recorded"] is True
        assert result["quality_state"] == "fail"


class TestSearchManufacturingOrders:
    async def test_search_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "MO/001",
                "product_id": [1, "Widget"],
                "state": "progress",
            }
        ]
        tool = SearchManufacturingOrders()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestGetCapacity:
    async def test_capacity_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "Assembly Line 1",
                "capacity": 100,
                "time_efficiency": 95.0,
                "working_state": "normal",
            }
        ]
        tool = GetCapacity()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_create_production_no_client(self):
        tool = CreateProduction()
        result = await tool.execute({"product_id": 1, "product_qty": 10, "bom_id": 1})
        assert "error" in result

    async def test_start_production_no_client(self):
        tool = StartProduction()
        result = await tool.execute({"production_id": 1})
        assert "error" in result

    async def test_complete_production_no_client(self):
        tool = CompleteProduction()
        result = await tool.execute({"production_id": 1})
        assert "error" in result

    async def test_plan_schedule_no_client(self):
        tool = PlanSchedule()
        result = await tool.execute({})
        assert "error" in result

    async def test_quality_check_no_client(self):
        tool = QualityCheck()
        result = await tool.execute({"check_id": 1, "quality_state": "pass"})
        assert "error" in result

    async def test_search_manufacturing_orders_no_client(self):
        tool = SearchManufacturingOrders()
        result = await tool.execute({})
        assert "error" in result

    async def test_get_capacity_no_client(self):
        tool = GetCapacity()
        result = await tool.execute({})
        assert "error" in result


class TestAllManufacturingTools:
    def test_all_tools_count(self):
        assert len(ALL_MANUFACTURING_TOOLS) == 8

    def test_all_tools_have_names(self):
        for tool in ALL_MANUFACTURING_TOOLS:
            assert tool.name != ""
            assert tool.domain == "manufacturing"
