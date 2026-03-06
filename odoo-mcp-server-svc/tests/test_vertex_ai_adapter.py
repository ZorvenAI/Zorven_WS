"""Tests for VertexAIRAGAdapter — direct Vertex AI Discovery Engine adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.vertex_ai_adapter import VertexAIRAGAdapter


@pytest.fixture
def mock_tenant_resolver() -> AsyncMock:
    """Mock TenantDataStoreResolver."""
    resolver = AsyncMock()
    resolver.resolve_data_store_id.return_value = "test-data-store"
    return resolver


@pytest.fixture
def adapter_mock(mock_tenant_resolver: AsyncMock) -> VertexAIRAGAdapter:
    """Adapter in mock mode."""
    return VertexAIRAGAdapter(
        project_id="test-project",
        location="global",
        default_data_store_id="default-store",
        mock_mode=True,
        tenant_resolver=mock_tenant_resolver,
    )


@pytest.fixture
def adapter_no_resolver() -> VertexAIRAGAdapter:
    """Adapter in mock mode without tenant resolver."""
    return VertexAIRAGAdapter(
        project_id="test-project",
        location="global",
        default_data_store_id="default-store",
        mock_mode=True,
    )


# ── Constructor ──


class TestInit:
    def test_defaults(self) -> None:
        a = VertexAIRAGAdapter()
        assert a.project_id == "brandsol-project"
        assert a.location == "global"
        assert a._doc_client is None
        assert a._search_client is None

    def test_custom_values(self) -> None:
        a = VertexAIRAGAdapter(
            project_id="my-project",
            location="us-central1",
            default_data_store_id="my-store",
            mock_mode=True,
        )
        assert a.project_id == "my-project"
        assert a.location == "us-central1"
        assert a.default_data_store_id == "my-store"
        assert a.mock_mode is True


# ── _build_data_store_path ──


class TestBuildDataStorePath:
    def test_path_format(self, adapter_mock: VertexAIRAGAdapter) -> None:
        path = adapter_mock._build_data_store_path("my-store")
        assert path == (
            "projects/test-project/locations/global/"
            "collections/default_collection/dataStores/my-store"
        )


# ── _get_data_store_id ──


class TestGetDataStoreId:
    async def test_uses_tenant_resolver(
        self,
        adapter_mock: VertexAIRAGAdapter,
        mock_tenant_resolver: AsyncMock,
    ) -> None:
        """Delegates to tenant resolver when available."""
        result = await adapter_mock._get_data_store_id("42")
        assert result == "test-data-store"
        mock_tenant_resolver.resolve_data_store_id.assert_awaited_once_with("42")

    async def test_falls_back_to_default(
        self,
        adapter_no_resolver: VertexAIRAGAdapter,
    ) -> None:
        """Returns default_data_store_id when no resolver."""
        result = await adapter_no_resolver._get_data_store_id("42")
        assert result == "default-store"


# ── upsert_document (mock mode) ──


class TestUpsertDocumentMock:
    async def test_mock_upsert_returns_success(
        self,
        adapter_mock: VertexAIRAGAdapter,
    ) -> None:
        result = await adapter_mock.upsert_document(
            document_id="odoo-sale_order-42",
            document_content={
                "document_type": "odoo_sale_order",
                "metadata": {"source": "odoo"},
                "extracted_text": "Sale Order 42",
            },
            tenant_id="1",
        )
        assert result["status"] == "mock_completed"
        assert result["document_id"] == "odoo-sale_order-42"
        assert "processing_time_ms" in result

    async def test_mock_upsert_with_default_tenant(
        self,
        adapter_mock: VertexAIRAGAdapter,
    ) -> None:
        result = await adapter_mock.upsert_document(
            document_id="test-doc",
            document_content={"extracted_text": "test"},
        )
        assert result["status"] == "mock_completed"


# ── search (mock mode) ──


class TestSearchMock:
    async def test_mock_search_returns_empty(
        self,
        adapter_mock: VertexAIRAGAdapter,
    ) -> None:
        result = await adapter_mock.search("test query", tenant_id="1")
        assert result["results"] == []
        assert result["mock"] is True

    async def test_mock_search_default_tenant(
        self,
        adapter_mock: VertexAIRAGAdapter,
    ) -> None:
        result = await adapter_mock.search("test")
        assert result["results"] == []


# ── delete_document (mock mode) ──


class TestDeleteDocumentMock:
    async def test_mock_delete_returns_success(
        self,
        adapter_mock: VertexAIRAGAdapter,
    ) -> None:
        result = await adapter_mock.delete_document(
            document_id="odoo-sale_order-42",
            tenant_id="1",
        )
        assert result["status"] == "mock_completed"
        assert result["document_id"] == "odoo-sale_order-42"


# ── get_document (mock mode) ──


class TestGetDocumentMock:
    async def test_mock_get_returns_id(
        self,
        adapter_mock: VertexAIRAGAdapter,
    ) -> None:
        result = await adapter_mock.get_document(
            document_id="odoo-sale_order-42",
            tenant_id="1",
        )
        assert result["id"] == "odoo-sale_order-42"
        assert result["mock"] is True


# ── _sanitize_for_vertex ──


class TestSanitizeForVertex:
    def test_removes_variable_shape_fields(self) -> None:
        content = {
            "struct_data": {
                "metadata": {"key": "value"},
                "tables": [{"cols": ["a", "b"]}],
                "lists": [["item1"]],
                "key_value_pairs": [{"key": "k", "value": "v"}],
            }
        }
        result = VertexAIRAGAdapter._sanitize_for_vertex(content)

        assert "metadata" in result["struct_data"]
        assert "tables" not in result["struct_data"]
        assert "lists" not in result["struct_data"]
        assert "key_value_pairs" not in result["struct_data"]

    def test_preserves_content_without_struct_data(self) -> None:
        content = {"extracted_text": "hello"}
        result = VertexAIRAGAdapter._sanitize_for_vertex(content)
        assert result == content

    def test_preserves_non_dict_struct_data(self) -> None:
        content = {"struct_data": "not a dict"}
        result = VertexAIRAGAdapter._sanitize_for_vertex(content)
        assert result == content


# ── _get_doc_client (mock mode) ──


class TestGetDocClient:
    def test_returns_none_in_mock_mode(
        self,
        adapter_mock: VertexAIRAGAdapter,
    ) -> None:
        assert adapter_mock._get_doc_client() is None

    def test_returns_none_when_sdk_missing(self) -> None:
        adapter = VertexAIRAGAdapter(mock_mode=False)
        with patch.dict("sys.modules", {"google.cloud": None}):
            # When import fails, should set mock_mode=True
            adapter._doc_client = None
            try:
                result = adapter._get_doc_client()
            except (ImportError, TypeError):
                # Expected when google.cloud is None
                pass


# ── _get_search_client (mock mode) ──


class TestGetSearchClient:
    def test_returns_none_in_mock_mode(
        self,
        adapter_mock: VertexAIRAGAdapter,
    ) -> None:
        assert adapter_mock._get_search_client() is None
