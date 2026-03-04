"""Tests for Website domain tools."""

from unittest.mock import AsyncMock

from app.tools.website.tools import (
    ALL_WEBSITE_TOOLS,
    CreatePage,
    ListProducts,
    ProcessEcommerceOrder,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCreatePage:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 15
        tool = CreatePage()
        result = await tool.execute({"name": "About Us", "url": "/about-us"}, ctx)
        assert result["id"] == 15
        assert result["model"] == "website.page"

    async def test_create_no_client(self):
        tool = CreatePage()
        result = await tool.execute({"name": "About Us", "url": "/about-us"})
        assert "error" in result


class TestListProducts:
    async def test_list_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "Widget Pro",
                "list_price": 29.99,
                "website_url": "/shop/widget-pro",
            }
        ]
        tool = ListProducts()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert result["model"] == "product.template"
        assert len(result["records"]) == 1


class TestProcessEcommerceOrder:
    async def test_process_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "S00001",
                "partner_id": [1, "Customer"],
                "state": "sale",
                "amount_total": 59.98,
            }
        ]
        tool = ProcessEcommerceOrder()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert result["model"] == "sale.order"
        assert len(result["records"]) == 1


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_list_products_no_client(self):
        tool = ListProducts()
        result = await tool.execute({})
        assert "error" in result

    async def test_process_ecommerce_order_no_client(self):
        tool = ProcessEcommerceOrder()
        result = await tool.execute({})
        assert "error" in result


class TestAllWebsiteTools:
    def test_all_tools_count(self):
        assert len(ALL_WEBSITE_TOOLS) == 3

    def test_all_tools_have_names(self):
        for tool in ALL_WEBSITE_TOOLS:
            assert tool.name != ""
            assert tool.domain == "website"
