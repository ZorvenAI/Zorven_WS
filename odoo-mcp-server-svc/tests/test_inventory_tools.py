"""Tests for Inventory & Purchase domain tools."""

from unittest.mock import AsyncMock

from app.tools.inventory.tools import (
    ALL_INVENTORY_TOOLS,
    CheckAvailability,
    ConfirmPurchaseOrder,
    CreateAdjustment,
    CreatePurchaseBill,
    CreateRFQ,
    CreateTransfer,
    ForecastReport,
    GetValuation,
    ManageLocations,
    ReceiveProducts,
    ValidateTransfer,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCheckAvailability:
    async def test_check_returns_picking_info(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.side_effect = [
            [
                {
                    "id": 1,
                    "name": "WH/OUT/001",
                    "state": "assigned",
                    "scheduled_date": "2026-03-10",
                    "picking_type_id": [1, "Delivery"],
                    "move_ids": [10, 11],
                }
            ],
            [
                {
                    "id": 10,
                    "product_id": [1, "Widget"],
                    "product_uom_qty": 5.0,
                    "quantity": 5.0,
                    "state": "assigned",
                },
            ],
        ]
        tool = CheckAvailability()
        result = await tool.execute({"picking_id": 1}, ctx)
        assert result["picking_id"] == 1
        assert result["state"] == "assigned"
        assert len(result["moves"]) == 1

    async def test_check_not_found(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = []
        tool = CheckAvailability()
        result = await tool.execute({"picking_id": 999}, ctx)
        assert "error" in result

    async def test_check_no_client(self):
        tool = CheckAvailability()
        result = await tool.execute({"picking_id": 1})
        assert "error" in result


class TestCreateTransfer:
    async def test_create_returns_picking_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 50
        tool = CreateTransfer()
        result = await tool.execute(
            {
                "picking_type_id": 1,
                "location_id": 10,
                "location_dest_id": 20,
                "move_lines": [{"product_id": 1, "product_uom_qty": 5.0}],
            },
            ctx,
        )
        assert result["picking_id"] == 50
        assert result["success"] is True


class TestValidateTransfer:
    async def test_validate_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = ValidateTransfer()
        result = await tool.execute({"picking_id": 50}, ctx)
        assert result["validated"] is True
        assert result["picking_id"] == 50


class TestCreateAdjustment:
    async def test_adjustment_existing_quant(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {"id": 5, "quantity": 10, "inventory_quantity": 0}
        ]
        ctx["rpc_client"].write.return_value = True
        ctx["rpc_client"].execute_kw.return_value = True
        tool = CreateAdjustment()
        result = await tool.execute(
            {
                "product_id": 1,
                "location_id": 10,
                "inventory_quantity": 15,
            },
            ctx,
        )
        assert result["applied"] is True
        assert result["quant_id"] == 5
        assert result["new_quantity"] == 15

    async def test_adjustment_new_quant(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = []
        ctx["rpc_client"].create.return_value = 99
        ctx["rpc_client"].execute_kw.return_value = True
        tool = CreateAdjustment()
        result = await tool.execute(
            {
                "product_id": 1,
                "location_id": 10,
                "inventory_quantity": 20,
            },
            ctx,
        )
        assert result["applied"] is True
        assert result["quant_id"] == 99


class TestGetValuation:
    async def test_valuation_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "product_id": [1, "Widget"],
                "quantity": 10,
                "value": 500,
            }
        ]
        tool = GetValuation()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestManageLocations:
    async def test_locations_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {"id": 1, "name": "Stock", "usage": "internal"}
        ]
        tool = ManageLocations()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestForecastReport:
    async def test_forecast_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "product_id": [1, "Widget"],
                "quantity": 50,
                "reserved_quantity": 10,
                "available_quantity": 40,
            }
        ]
        tool = ForecastReport()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestCreateRFQ:
    async def test_create_rfq_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 30
        tool = CreateRFQ()
        result = await tool.execute(
            {
                "partner_id": 5,
                "order_lines": [{"product_id": 1, "product_qty": 100}],
            },
            ctx,
        )
        assert result["order_id"] == 30
        assert result["success"] is True


class TestConfirmPurchaseOrder:
    async def test_confirm_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = ConfirmPurchaseOrder()
        result = await tool.execute({"order_id": 30}, ctx)
        assert result["confirmed"] is True
        assert result["order_id"] == 30


class TestReceiveProducts:
    async def test_receive_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        ctx["rpc_client"].execute_kw.return_value = True
        tool = ReceiveProducts()
        result = await tool.execute(
            {
                "picking_id": 50,
                "move_quantities": [{"move_id": 10, "quantity": 100}],
            },
            ctx,
        )
        assert result["received"] is True
        assert result["picking_id"] == 50


class TestCreatePurchaseBill:
    async def test_create_bill_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = {"res_id": 200}
        tool = CreatePurchaseBill()
        result = await tool.execute({"order_id": 30}, ctx)
        assert result["bill_created"] is True
        assert result["order_id"] == 30


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_create_transfer_no_client(self):
        tool = CreateTransfer()
        result = await tool.execute(
            {
                "picking_type_id": 1,
                "location_id": 1,
                "location_dest_id": 2,
                "move_lines": [{"product_id": 1, "product_uom_qty": 1}],
            }
        )
        assert "error" in result

    async def test_validate_transfer_no_client(self):
        tool = ValidateTransfer()
        result = await tool.execute({"picking_id": 1})
        assert "error" in result

    async def test_create_adjustment_no_client(self):
        tool = CreateAdjustment()
        result = await tool.execute(
            {"product_id": 1, "location_id": 1, "inventory_quantity": 10}
        )
        assert "error" in result

    async def test_get_valuation_no_client(self):
        tool = GetValuation()
        result = await tool.execute({})
        assert "error" in result

    async def test_manage_locations_no_client(self):
        tool = ManageLocations()
        result = await tool.execute({})
        assert "error" in result

    async def test_forecast_report_no_client(self):
        tool = ForecastReport()
        result = await tool.execute({})
        assert "error" in result

    async def test_create_rfq_no_client(self):
        tool = CreateRFQ()
        result = await tool.execute(
            {"partner_id": 1, "order_lines": [{"product_id": 1, "product_qty": 10}]}
        )
        assert "error" in result

    async def test_confirm_purchase_order_no_client(self):
        tool = ConfirmPurchaseOrder()
        result = await tool.execute({"order_id": 1})
        assert "error" in result

    async def test_receive_products_no_client(self):
        tool = ReceiveProducts()
        result = await tool.execute({"picking_id": 1})
        assert "error" in result

    async def test_create_purchase_bill_no_client(self):
        tool = CreatePurchaseBill()
        result = await tool.execute({"order_id": 1})
        assert "error" in result


class TestAllInventoryTools:
    def test_all_tools_count(self):
        assert len(ALL_INVENTORY_TOOLS) == 11

    def test_all_tools_have_names(self):
        for tool in ALL_INVENTORY_TOOLS:
            assert tool.name != ""
            assert tool.domain == "inventory"
