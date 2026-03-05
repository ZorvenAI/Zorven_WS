"""Tests for MCP resources — Odoo + RAG resources via ResourceRegistry."""

import json
from unittest.mock import AsyncMock

import pytest

from app.mcp.resources import ResourceRegistry

# ── Fixtures ──


@pytest.fixture
def mock_rpc_client() -> AsyncMock:
    """Mock Odoo RPC client."""
    client = AsyncMock()
    client.fields_get.return_value = {
        "name": {"type": "char", "string": "Name"},
        "email": {"type": "char", "string": "Email"},
    }
    client.search_read.return_value = [
        {"id": 1, "name": "Test Record", "state": "active"}
    ]
    client.search_count.return_value = 42
    return client


@pytest.fixture
def mock_rag_client() -> AsyncMock:
    """Mock RAG client."""
    client = AsyncMock()
    client.query.return_value = {
        "results": [{"text": "Knowledge result", "score": 0.95}]
    }
    client.list_documents.return_value = {
        "documents": [{"id": "doc-1", "title": "Sales Policy"}]
    }
    client.get_document.return_value = {
        "id": "doc-1",
        "content": "Sales policy details...",
    }
    client.get_context.return_value = {"results": [{"text": "Context for record"}]}
    client.get_stats.return_value = {
        "total_documents": 150,
        "total_chunks": 1200,
        "status": "healthy",
    }
    return client


@pytest.fixture
def registry_full(
    mock_rpc_client: AsyncMock, mock_rag_client: AsyncMock
) -> ResourceRegistry:
    """Registry with both RPC and RAG clients."""
    return ResourceRegistry(rpc_client=mock_rpc_client, rag_client=mock_rag_client)


@pytest.fixture
def registry_no_clients() -> ResourceRegistry:
    """Registry without any clients."""
    return ResourceRegistry()


@pytest.fixture
def registry_rpc_only(mock_rpc_client: AsyncMock) -> ResourceRegistry:
    """Registry with only an RPC client."""
    return ResourceRegistry(rpc_client=mock_rpc_client)


@pytest.fixture
def registry_rag_only(mock_rag_client: AsyncMock) -> ResourceRegistry:
    """Registry with only a RAG client."""
    return ResourceRegistry(rag_client=mock_rag_client)


# ── list_resources ──


class TestListResources:
    """Test list_resources() returns the correct set of resources."""

    def test_returns_16_resources(self, registry_no_clients: ResourceRegistry) -> None:
        """Total resource count is 16 (11 Odoo + 5 RAG)."""
        resources = registry_no_clients.list_resources()
        assert len(resources) == 16

    def test_11_odoo_resources(self, registry_no_clients: ResourceRegistry) -> None:
        """11 resources have odoo:// URIs."""
        resources = registry_no_clients.list_resources()
        odoo = [r for r in resources if str(r.uri).startswith("odoo://")]
        assert len(odoo) == 11

    def test_5_rag_resources(self, registry_no_clients: ResourceRegistry) -> None:
        """5 resources have rag:// URIs."""
        resources = registry_no_clients.list_resources()
        rag = [r for r in resources if str(r.uri).startswith("rag://")]
        assert len(rag) == 5

    def test_all_resources_have_name(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Every resource has a non-empty name."""
        for r in registry_no_clients.list_resources():
            assert r.name, f"Resource {r.uri} has no name"

    def test_all_resources_have_description(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Every resource has a non-empty description."""
        for r in registry_no_clients.list_resources():
            assert r.description, f"Resource {r.uri} has no description"

    def test_all_resources_are_json_mime(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """All resources declare application/json MIME type."""
        for r in registry_no_clients.list_resources():
            assert r.mimeType == "application/json"

    def test_expected_odoo_uris(self, registry_no_clients: ResourceRegistry) -> None:
        """Verify specific Odoo resource URIs are present."""
        resources = registry_no_clients.list_resources()
        uris = {str(r.uri) for r in resources}
        # Pydantic AnyUrl encodes curly braces: {model} -> %7Bmodel%7D
        expected = {
            "odoo://schema/%7Bmodel%7D",
            "odoo://config/modules",
            "odoo://config/company",
            "odoo://config/users",
            "odoo://dashboard/sales",
            "odoo://dashboard/inventory",
            "odoo://dashboard/accounting",
            "odoo://dashboard/hr",
            "odoo://rbac/effective_roles",
            "odoo://rbac/pending_approvals",
            "odoo://tenant/info",
        }
        assert expected.issubset(uris)

    def test_expected_rag_uris(self, registry_no_clients: ResourceRegistry) -> None:
        """Verify specific RAG resource URIs are present."""
        resources = registry_no_clients.list_resources()
        uris = {str(r.uri) for r in resources}
        # Pydantic AnyUrl encodes curly braces: {query} -> %7Bquery%7D
        expected = {
            "rag://knowledge/%7Bquery%7D",
            "rag://documents/list",
            "rag://documents/%7Bdoc_id%7D",
            "rag://context/%7Bmodel%7D/%7Brecord_id%7D",
            "rag://stats",
        }
        assert expected.issubset(uris)

    def test_list_does_not_depend_on_clients(self) -> None:
        """list_resources() works regardless of client availability."""
        for rpc, rag in [(None, None), (AsyncMock(), None), (None, AsyncMock())]:
            registry = ResourceRegistry(rpc_client=rpc, rag_client=rag)
            assert len(registry.list_resources()) == 16


# ── read() — Odoo schema resource ──


class TestReadSchema:
    """Test read('odoo://schema/...')."""

    async def test_read_schema_with_client(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns field definitions for the requested model."""
        result = await registry_full.read("odoo://schema/res.partner")
        data = json.loads(result)

        assert data["model"] == "res.partner"
        assert "fields" in data
        assert "name" in data["fields"]
        mock_rpc_client.fields_get.assert_awaited_once_with("res.partner")

    async def test_read_schema_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns error when no RPC client is available."""
        result = await registry_no_clients.read("odoo://schema/res.partner")
        data = json.loads(result)

        assert data["model"] == "res.partner"
        assert "error" in data
        assert "No Odoo connection" in data["error"]

    async def test_read_schema_rpc_exception(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns error when fields_get raises an exception."""
        mock_rpc_client.fields_get.side_effect = Exception("Access denied")

        result = await registry_full.read("odoo://schema/sale.order")
        data = json.loads(result)

        assert data["model"] == "sale.order"
        assert "error" in data
        assert "Access denied" in data["error"]


# ── read() — Odoo config resources ──


class TestReadConfig:
    """Test read() for odoo://config/* resources."""

    async def test_read_modules(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns installed modules list."""
        mock_rpc_client.search_read.return_value = [
            {"name": "sale", "shortdesc": "Sales", "state": "installed"}
        ]

        result = await registry_full.read("odoo://config/modules")
        data = json.loads(result)

        assert "modules" in data
        assert data["modules"][0]["name"] == "sale"

    async def test_read_modules_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns error when no RPC client for modules."""
        result = await registry_no_clients.read("odoo://config/modules")
        data = json.loads(result)

        assert "error" in data

    async def test_read_company(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns company info."""
        mock_rpc_client.search_read.return_value = [
            {"name": "My Company", "email": "info@company.com"}
        ]

        result = await registry_full.read("odoo://config/company")
        data = json.loads(result)

        assert "company" in data
        assert data["company"]["name"] == "My Company"

    async def test_read_company_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns error when no RPC client for company."""
        result = await registry_no_clients.read("odoo://config/company")
        data = json.loads(result)

        assert "error" in data

    async def test_read_company_empty_result(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns empty company when search_read returns empty list."""
        mock_rpc_client.search_read.return_value = []

        result = await registry_full.read("odoo://config/company")
        data = json.loads(result)

        assert data["company"] == {}

    async def test_read_users(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns user list."""
        mock_rpc_client.search_read.return_value = [{"name": "Admin", "login": "admin"}]

        result = await registry_full.read("odoo://config/users")
        data = json.loads(result)

        assert "users" in data

    async def test_read_users_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns error when no RPC client for users."""
        result = await registry_no_clients.read("odoo://config/users")
        data = json.loads(result)

        assert "error" in data


# ── read() — Odoo dashboard resources ──


class TestReadDashboards:
    """Test read() for odoo://dashboard/* resources."""

    async def test_read_sales_dashboard(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns sales dashboard with orders and opportunities."""
        mock_rpc_client.search_read.return_value = [
            {"name": "SO001", "amount_total": 1000, "state": "sale"}
        ]
        mock_rpc_client.search_count.return_value = 15

        result = await registry_full.read("odoo://dashboard/sales")
        data = json.loads(result)

        assert "recent_orders" in data
        assert "open_opportunities" in data
        assert data["open_opportunities"] == 15

    async def test_read_sales_dashboard_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns error when no RPC client for sales dashboard."""
        result = await registry_no_clients.read("odoo://dashboard/sales")
        data = json.loads(result)

        assert "error" in data

    async def test_read_inventory_dashboard(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns inventory dashboard with pending transfers."""
        mock_rpc_client.search_read.return_value = [
            {"name": "WH/OUT/001", "state": "assigned"}
        ]

        result = await registry_full.read("odoo://dashboard/inventory")
        data = json.loads(result)

        assert "pending_transfers" in data

    async def test_read_inventory_dashboard_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        result = await registry_no_clients.read("odoo://dashboard/inventory")
        data = json.loads(result)
        assert "error" in data

    async def test_read_accounting_dashboard(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns accounting dashboard with unpaid invoices."""
        mock_rpc_client.search_read.return_value = [
            {"name": "INV/2026/0001", "amount_total": 500}
        ]

        result = await registry_full.read("odoo://dashboard/accounting")
        data = json.loads(result)

        assert "unpaid_invoices" in data

    async def test_read_accounting_dashboard_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        result = await registry_no_clients.read("odoo://dashboard/accounting")
        data = json.loads(result)
        assert "error" in data

    async def test_read_hr_dashboard(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns HR dashboard with employee count and pending leaves."""
        mock_rpc_client.search_count.side_effect = [25, 3]

        result = await registry_full.read("odoo://dashboard/hr")
        data = json.loads(result)

        assert data["active_employees"] == 25
        assert data["pending_leaves"] == 3

    async def test_read_hr_dashboard_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        result = await registry_no_clients.read("odoo://dashboard/hr")
        data = json.loads(result)
        assert "error" in data

    async def test_dashboard_handles_rpc_exception(
        self,
        registry_full: ResourceRegistry,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Dashboard gracefully handles RPC exceptions."""
        mock_rpc_client.search_read.side_effect = Exception("Timeout")

        result = await registry_full.read("odoo://dashboard/sales")
        data = json.loads(result)

        assert "error" in data


# ── read() — RBAC and tenant resources ──


class TestReadRBACAndTenant:
    """Test read() for RBAC and tenant info resources."""

    async def test_read_effective_roles(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns roles with RBAC context note."""
        result = await registry_no_clients.read("odoo://rbac/effective_roles")
        data = json.loads(result)

        assert "roles" in data
        assert data["roles"] == []
        assert "RBAC context required" in data["note"]

    async def test_read_pending_approvals(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns empty pending approvals list."""
        result = await registry_no_clients.read("odoo://rbac/pending_approvals")
        data = json.loads(result)

        assert "approvals" in data
        assert data["approvals"] == []

    async def test_read_tenant_info(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns default tenant configuration."""
        result = await registry_no_clients.read("odoo://tenant/info")
        data = json.loads(result)

        assert data["tenant"] == "default"
        assert data["status"] == "active"


# ── read() — RAG resources ──


class TestReadRAGResources:
    """Test read() for rag://* resources."""

    async def test_read_rag_knowledge_query(
        self,
        registry_full: ResourceRegistry,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Queries RAG knowledge store and returns results."""
        result = await registry_full.read("rag://knowledge/sales policy")
        data = json.loads(result)

        assert "results" in data
        mock_rag_client.query.assert_awaited_once_with("sales policy")

    async def test_read_rag_documents_list(
        self,
        registry_full: ResourceRegistry,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Lists documents from the RAG store."""
        result = await registry_full.read("rag://documents/list")
        data = json.loads(result)

        assert "documents" in data
        mock_rag_client.list_documents.assert_awaited_once()

    async def test_read_rag_document_by_id(
        self,
        registry_full: ResourceRegistry,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Gets a specific document by ID."""
        result = await registry_full.read("rag://documents/doc-1")
        data = json.loads(result)

        assert data["id"] == "doc-1"
        mock_rag_client.get_document.assert_awaited_once_with("doc-1")

    async def test_read_rag_context_for_record(
        self,
        registry_full: ResourceRegistry,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Gets RAG context for an Odoo record."""
        result = await registry_full.read("rag://context/res.partner/42")
        data = json.loads(result)

        assert "results" in data
        mock_rag_client.get_context.assert_awaited_once_with("res.partner", 42)

    async def test_read_rag_stats(
        self,
        registry_full: ResourceRegistry,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Returns RAG store statistics."""
        result = await registry_full.read("rag://stats")
        data = json.loads(result)

        assert data["total_documents"] == 150
        assert data["status"] == "healthy"
        mock_rag_client.get_stats.assert_awaited_once()

    async def test_read_rag_resource_no_client(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns error when no RAG client for any rag:// resource."""
        for uri in [
            "rag://stats",
            "rag://knowledge/test",
            "rag://documents/list",
            "rag://documents/doc-1",
            "rag://context/res.partner/42",
        ]:
            result = await registry_no_clients.read(uri)
            data = json.loads(result)
            assert "error" in data, f"Expected error for {uri}"
            assert "RAG service not configured" in data["error"]

    async def test_read_rag_handles_exception(
        self,
        registry_rag_only: ResourceRegistry,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Returns error when RAG client raises an exception."""
        mock_rag_client.get_stats.side_effect = Exception("Connection refused")

        result = await registry_rag_only.read("rag://stats")
        data = json.loads(result)

        assert "error" in data
        assert "Connection refused" in data["error"]

    async def test_read_unknown_rag_resource(
        self, registry_rag_only: ResourceRegistry
    ) -> None:
        """Returns error for an unrecognized rag:// URI pattern."""
        result = await registry_rag_only.read("rag://unknown/path")
        data = json.loads(result)

        assert "error" in data

    async def test_read_rag_context_invalid_parts(
        self, registry_rag_only: ResourceRegistry
    ) -> None:
        """Returns error for rag://context/ with wrong number of path parts."""
        result = await registry_rag_only.read("rag://context/res.partner")
        data = json.loads(result)

        # Should not match the 2-part split so falls through to unknown
        assert "error" in data


# ── read() — Unknown resources ──


class TestReadUnknown:
    """Test read() for unrecognized URIs."""

    async def test_read_unknown_uri(
        self, registry_no_clients: ResourceRegistry
    ) -> None:
        """Returns error for completely unknown URI scheme."""
        result = await registry_no_clients.read("unknown://resource")
        data = json.loads(result)

        assert "error" in data
        assert "Unknown resource" in data["error"]

    async def test_read_empty_uri(self, registry_no_clients: ResourceRegistry) -> None:
        """Returns error for empty URI."""
        result = await registry_no_clients.read("")
        data = json.loads(result)

        assert "error" in data


# ── Constructor tests ──


class TestResourceRegistryInit:
    """Test ResourceRegistry initialization."""

    def test_init_with_both_clients(
        self, mock_rpc_client: AsyncMock, mock_rag_client: AsyncMock
    ) -> None:
        registry = ResourceRegistry(
            rpc_client=mock_rpc_client, rag_client=mock_rag_client
        )
        assert registry.rpc_client is mock_rpc_client
        assert registry.rag_client is mock_rag_client

    def test_init_defaults_to_none(self) -> None:
        registry = ResourceRegistry()
        assert registry.rpc_client is None
        assert registry.rag_client is None

    def test_init_rpc_only(self, mock_rpc_client: AsyncMock) -> None:
        registry = ResourceRegistry(rpc_client=mock_rpc_client)
        assert registry.rpc_client is mock_rpc_client
        assert registry.rag_client is None

    def test_init_rag_only(self, mock_rag_client: AsyncMock) -> None:
        registry = ResourceRegistry(rag_client=mock_rag_client)
        assert registry.rpc_client is None
        assert registry.rag_client is mock_rag_client
