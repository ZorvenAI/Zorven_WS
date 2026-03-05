"""Tests for MCP resources."""

import json
from unittest.mock import AsyncMock

from app.mcp.resources import ResourceRegistry


class TestResourceRegistry:
    def test_list_resources_returns_16(self):
        registry = ResourceRegistry()
        resources = registry.list_resources()
        assert len(resources) == 16

    def test_odoo_resources_count(self):
        registry = ResourceRegistry()
        resources = registry.list_resources()
        odoo = [r for r in resources if str(r.uri).startswith("odoo://")]
        assert len(odoo) == 11

    def test_rag_resources_count(self):
        registry = ResourceRegistry()
        resources = registry.list_resources()
        rag = [r for r in resources if str(r.uri).startswith("rag://")]
        assert len(rag) == 5

    async def test_read_schema_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://schema/res.partner")
        data = json.loads(result)
        assert data["model"] == "res.partner"
        assert "error" in data

    async def test_read_tenant_info(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://tenant/info")
        data = json.loads(result)
        assert data["tenant"] == "default"

    async def test_read_unknown_resource(self):
        registry = ResourceRegistry()
        result = await registry.read("unknown://resource")
        data = json.loads(result)
        assert "error" in data

    async def test_read_rag_resource_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("rag://stats")
        data = json.loads(result)
        assert "error" in data


class TestResourceRegistryRPCSuccess:
    """RPC success paths with mock RPC client."""

    async def test_read_modules_success(self):
        rpc = AsyncMock()
        rpc.search_read.return_value = [{"name": "sale", "state": "installed"}]
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://config/modules")
        data = json.loads(result)
        assert "modules" in data
        assert len(data["modules"]) == 1

    async def test_read_company_success(self):
        rpc = AsyncMock()
        rpc.search_read.return_value = [{"name": "My Company", "email": "a@b.com"}]
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://config/company")
        data = json.loads(result)
        assert data["company"]["name"] == "My Company"

    async def test_read_company_empty(self):
        rpc = AsyncMock()
        rpc.search_read.return_value = []
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://config/company")
        data = json.loads(result)
        assert data["company"] == {}

    async def test_read_users_success(self):
        rpc = AsyncMock()
        rpc.search_read.return_value = [{"name": "Admin", "login": "admin"}]
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://config/users")
        data = json.loads(result)
        assert "users" in data

    async def test_read_sales_dashboard_success(self):
        rpc = AsyncMock()
        rpc.search_read.return_value = [{"name": "SO001", "amount_total": 100}]
        rpc.search_count.return_value = 5
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://dashboard/sales")
        data = json.loads(result)
        assert "recent_orders" in data
        assert data["open_opportunities"] == 5

    async def test_read_inventory_dashboard_success(self):
        rpc = AsyncMock()
        rpc.search_read.return_value = [{"name": "WH/OUT/001"}]
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://dashboard/inventory")
        data = json.loads(result)
        assert "pending_transfers" in data

    async def test_read_accounting_dashboard_success(self):
        rpc = AsyncMock()
        rpc.search_read.return_value = [{"name": "INV/001"}]
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://dashboard/accounting")
        data = json.loads(result)
        assert "unpaid_invoices" in data

    async def test_read_hr_dashboard_success(self):
        rpc = AsyncMock()
        rpc.search_count.side_effect = [42, 3]
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://dashboard/hr")
        data = json.loads(result)
        assert data["active_employees"] == 42
        assert data["pending_leaves"] == 3

    async def test_read_schema_success(self):
        rpc = AsyncMock()
        rpc.fields_get.return_value = {"name": {"type": "char"}}
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://schema/res.partner")
        data = json.loads(result)
        assert data["model"] == "res.partner"
        assert "name" in data["fields"]


class TestResourceRegistryRPCException:
    """RPC exception paths."""

    async def test_read_schema_exception(self):
        rpc = AsyncMock()
        rpc.fields_get.side_effect = RuntimeError("timeout")
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://schema/res.partner")
        data = json.loads(result)
        assert "timeout" in data["error"]

    async def test_read_modules_exception(self):
        rpc = AsyncMock()
        rpc.search_read.side_effect = RuntimeError("fail")
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://config/modules")
        data = json.loads(result)
        assert "fail" in data["error"]

    async def test_read_company_exception(self):
        rpc = AsyncMock()
        rpc.search_read.side_effect = RuntimeError("fail")
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://config/company")
        data = json.loads(result)
        assert "error" in data

    async def test_read_users_exception(self):
        rpc = AsyncMock()
        rpc.search_read.side_effect = RuntimeError("fail")
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://config/users")
        data = json.loads(result)
        assert "error" in data

    async def test_read_sales_dashboard_exception(self):
        rpc = AsyncMock()
        rpc.search_read.side_effect = RuntimeError("fail")
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://dashboard/sales")
        data = json.loads(result)
        assert "error" in data

    async def test_read_inventory_dashboard_exception(self):
        rpc = AsyncMock()
        rpc.search_read.side_effect = RuntimeError("fail")
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://dashboard/inventory")
        data = json.loads(result)
        assert "error" in data

    async def test_read_accounting_dashboard_exception(self):
        rpc = AsyncMock()
        rpc.search_read.side_effect = RuntimeError("fail")
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://dashboard/accounting")
        data = json.loads(result)
        assert "error" in data

    async def test_read_hr_dashboard_exception(self):
        rpc = AsyncMock()
        rpc.search_count.side_effect = RuntimeError("fail")
        registry = ResourceRegistry(rpc_client=rpc)
        result = await registry.read("odoo://dashboard/hr")
        data = json.loads(result)
        assert "error" in data


class TestResourceRegistryNoClient:
    """No-RPC-client paths for all dashboards/config."""

    async def test_read_modules_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://config/modules")
        data = json.loads(result)
        assert "error" in data

    async def test_read_company_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://config/company")
        data = json.loads(result)
        assert "error" in data

    async def test_read_users_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://config/users")
        data = json.loads(result)
        assert "error" in data

    async def test_read_sales_dashboard_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://dashboard/sales")
        data = json.loads(result)
        assert "error" in data

    async def test_read_inventory_dashboard_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://dashboard/inventory")
        data = json.loads(result)
        assert "error" in data

    async def test_read_accounting_dashboard_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://dashboard/accounting")
        data = json.loads(result)
        assert "error" in data

    async def test_read_hr_dashboard_no_client(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://dashboard/hr")
        data = json.loads(result)
        assert "error" in data


class TestResourceRegistryStaticURIs:
    """Static URI paths (RBAC)."""

    async def test_read_rbac_effective_roles(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://rbac/effective_roles")
        data = json.loads(result)
        assert "roles" in data

    async def test_read_rbac_pending_approvals(self):
        registry = ResourceRegistry()
        result = await registry.read("odoo://rbac/pending_approvals")
        data = json.loads(result)
        assert "approvals" in data


class TestResourceRegistryRAG:
    """RAG resource paths with mock client."""

    async def test_read_rag_knowledge(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": []}
        registry = ResourceRegistry(rag_client=rag)
        result = await registry.read("rag://knowledge/test query")
        data = json.loads(result)
        assert "results" in data

    async def test_read_rag_documents_list(self):
        rag = AsyncMock()
        rag.list_documents.return_value = {"documents": []}
        registry = ResourceRegistry(rag_client=rag)
        result = await registry.read("rag://documents/list")
        data = json.loads(result)
        assert "documents" in data

    async def test_read_rag_document_by_id(self):
        rag = AsyncMock()
        rag.get_document.return_value = {"id": "doc1", "content": "data"}
        registry = ResourceRegistry(rag_client=rag)
        result = await registry.read("rag://documents/doc1")
        data = json.loads(result)
        assert data["id"] == "doc1"

    async def test_read_rag_context(self):
        rag = AsyncMock()
        rag.get_context.return_value = {"context": "data"}
        registry = ResourceRegistry(rag_client=rag)
        result = await registry.read("rag://context/res.partner/42")
        data = json.loads(result)
        assert "context" in data

    async def test_read_rag_context_invalid_parts(self):
        rag = AsyncMock()
        registry = ResourceRegistry(rag_client=rag)
        result = await registry.read("rag://context/only_one_part")
        data = json.loads(result)
        assert "error" in data

    async def test_read_rag_stats(self):
        rag = AsyncMock()
        rag.get_stats.return_value = {"total": 100}
        registry = ResourceRegistry(rag_client=rag)
        result = await registry.read("rag://stats")
        data = json.loads(result)
        assert data["total"] == 100

    async def test_read_rag_exception(self):
        rag = AsyncMock()
        rag.query.side_effect = RuntimeError("rag fail")
        registry = ResourceRegistry(rag_client=rag)
        result = await registry.read("rag://knowledge/test")
        data = json.loads(result)
        assert "rag fail" in data["error"]

    async def test_read_rag_unknown_uri(self):
        rag = AsyncMock()
        registry = ResourceRegistry(rag_client=rag)
        result = await registry.read("rag://unknown/path")
        data = json.loads(result)
        assert "Unknown RAG resource" in data["error"]
