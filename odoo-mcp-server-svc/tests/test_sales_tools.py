"""Tests for Sales domain tools."""

from unittest.mock import AsyncMock

from app.tools.sales.tools import (
    ALL_SALES_TOOLS,
    AddOrderLine,
    ApplyDiscount,
    CancelOrder,
    ConfirmOrder,
    CreateInvoice,
    CreateQuotation,
    GetOrderDetails,
    SearchOrders,
    SendQuotation,
    UpdatePricelist,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCreateQuotation:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 10
        tool = CreateQuotation()
        result = await tool.execute({"partner_id": 1}, ctx)
        assert result["id"] == 10
        assert result["partner_id"] == 1

    async def test_create_no_client(self):
        tool = CreateQuotation()
        result = await tool.execute({"partner_id": 1})
        assert "error" in result


class TestAddOrderLine:
    async def test_add_line_returns_ids(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 55
        tool = AddOrderLine()
        result = await tool.execute({"order_id": 10, "product_id": 7}, ctx)
        assert result["line_id"] == 55
        assert result["order_id"] == 10
        assert result["product_id"] == 7


class TestConfirmOrder:
    async def test_confirm_returns_status(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = ConfirmOrder()
        result = await tool.execute({"order_id": 10}, ctx)
        assert result["status"] == "confirmed"
        assert result["id"] == 10


class TestCancelOrder:
    async def test_cancel_returns_status(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = CancelOrder()
        result = await tool.execute({"order_id": 10}, ctx)
        assert result["status"] == "cancelled"
        assert result["id"] == 10


class TestCreateInvoice:
    async def test_create_invoice_returns_ids(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = [100]
        tool = CreateInvoice()
        result = await tool.execute({"order_id": 10}, ctx)
        assert result["order_id"] == 10
        assert result["invoice_ids"] == [100]


class TestApplyDiscount:
    async def test_apply_discount_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = ApplyDiscount()
        result = await tool.execute({"line_ids": [1, 2], "discount": 15.0}, ctx)
        assert result["success"] is True
        assert result["discount"] == 15.0
        assert result["line_ids"] == [1, 2]


class TestSearchOrders:
    async def test_search_returns_orders(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {"id": 1, "name": "SO001", "state": "sale"}
        ]
        tool = SearchOrders()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["orders"]) == 1


class TestGetOrderDetails:
    async def test_get_details_returns_order(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = [
            {
                "id": 10,
                "name": "SO010",
                "partner_id": [1, "Test"],
                "state": "sale",
                "order_line": [1, 2],
                "amount_total": 500.0,
            }
        ]
        ctx["rpc_client"].search_read.return_value = [
            {"id": 1, "product_id": [7, "Widget"], "price_subtotal": 250.0},
            {"id": 2, "product_id": [8, "Gadget"], "price_subtotal": 250.0},
        ]
        tool = GetOrderDetails()
        result = await tool.execute({"order_id": 10}, ctx)
        assert "order" in result
        assert result["order"]["name"] == "SO010"
        assert len(result["order"]["lines"]) == 2

    async def test_get_details_not_found(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = []
        tool = GetOrderDetails()
        result = await tool.execute({"order_id": 999}, ctx)
        assert "error" in result


class TestUpdatePricelist:
    async def test_update_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = UpdatePricelist()
        result = await tool.execute({"order_id": 10, "pricelist_id": 2}, ctx)
        assert result["success"] is True
        assert result["pricelist_id"] == 2


class TestSendQuotation:
    async def test_send_returns_status(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = SendQuotation()
        result = await tool.execute({"order_id": 10}, ctx)
        assert result["status"] == "sent"
        assert result["id"] == 10


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_add_order_line_no_client(self):
        tool = AddOrderLine()
        result = await tool.execute({"order_id": 1, "product_id": 1})
        assert "error" in result

    async def test_confirm_order_no_client(self):
        tool = ConfirmOrder()
        result = await tool.execute({"order_id": 1})
        assert "error" in result

    async def test_cancel_order_no_client(self):
        tool = CancelOrder()
        result = await tool.execute({"order_id": 1})
        assert "error" in result

    async def test_create_invoice_no_client(self):
        tool = CreateInvoice()
        result = await tool.execute({"order_id": 1})
        assert "error" in result

    async def test_apply_discount_no_client(self):
        tool = ApplyDiscount()
        result = await tool.execute({"line_ids": [1], "discount": 10.0})
        assert "error" in result

    async def test_search_orders_no_client(self):
        tool = SearchOrders()
        result = await tool.execute({})
        assert "error" in result

    async def test_get_order_details_no_client(self):
        tool = GetOrderDetails()
        result = await tool.execute({"order_id": 1})
        assert "error" in result

    async def test_update_pricelist_no_client(self):
        tool = UpdatePricelist()
        result = await tool.execute({"order_id": 1, "pricelist_id": 1})
        assert "error" in result

    async def test_send_quotation_no_client(self):
        tool = SendQuotation()
        result = await tool.execute({"order_id": 1})
        assert "error" in result


class TestAllSalesTools:
    def test_all_tools_count(self):
        assert len(ALL_SALES_TOOLS) == 10

    def test_all_tools_have_names(self):
        for tool in ALL_SALES_TOOLS:
            assert tool.name != ""
            assert tool.domain == "sales"
