"""Tests for RAG client — facade for Vertex AI (direct) or HTTP fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.client import RAGClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(json_data):
    """Create a mock httpx.Response with given JSON data."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _make_client_with_mock_http(json_data=None, side_effect=None):
    """Create a RAGClient (HTTP fallback) with a pre-injected mock HTTP client.

    Returns (rag_client, mock_http_client).
    """
    client = RAGClient("http://test:8070")
    mock_http = AsyncMock()

    if side_effect is not None:
        mock_http.post.side_effect = side_effect
        mock_http.get.side_effect = side_effect
        mock_http.delete.side_effect = side_effect
    else:
        resp = _mock_response(json_data or {})
        mock_http.post.return_value = resp
        mock_http.get.return_value = resp
        mock_http.delete.return_value = resp

    client._client = mock_http
    return client, mock_http


# ---------------------------------------------------------------------------
# _get_client (lazy initialization)
# ---------------------------------------------------------------------------


class TestGetClient:
    async def test_lazy_initialization(self):
        """_get_client creates httpx.AsyncClient on first call."""
        client = RAGClient("http://test:8070")
        assert client._client is None
        with patch("app.rag.client.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            result = await client._get_client()
            assert result is mock_instance
            mock_cls.assert_called_once_with(base_url="http://test:8070", timeout=30.0)

    async def test_reuses_existing_client(self):
        """_get_client returns existing client on subsequent calls."""
        client = RAGClient("http://test:8070")
        mock_http = AsyncMock()
        client._client = mock_http
        result = await client._get_client()
        assert result is mock_http


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


class TestClose:
    async def test_close_when_no_client(self):
        """close() is safe when _client is None."""
        client = RAGClient("http://test:8070")
        assert client._client is None
        await client.close()  # Should not raise

    async def test_close_when_client_exists(self):
        """close() calls aclose() and sets _client to None."""
        client = RAGClient("http://test:8070")
        mock_http = AsyncMock()
        client._client = mock_http
        await client.close()
        mock_http.aclose.assert_awaited_once()
        assert client._client is None


# ---------------------------------------------------------------------------
# _use_vertex property
# ---------------------------------------------------------------------------


class TestUseVertex:
    def test_false_when_no_adapter(self):
        client = RAGClient("http://test:8070")
        assert client._use_vertex is False

    def test_true_when_adapter_provided(self):
        mock_adapter = AsyncMock()
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)
        assert client._use_vertex is True


# ---------------------------------------------------------------------------
# query() — HTTP fallback
# ---------------------------------------------------------------------------


class TestQueryHTTP:
    async def test_success(self):
        client, mock_http = _make_client_with_mock_http(
            {"results": [{"text": "answer"}]}
        )
        result = await client.query("test query", tenant_id="t1", top_k=3)
        assert result == {"results": [{"text": "answer"}]}
        mock_http.post.assert_awaited_once_with(
            "/v1/query",
            json={"query": "test query", "namespace": "t1", "top_k": 3},
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_default_params(self):
        client, mock_http = _make_client_with_mock_http({"results": []})
        await client.query("q")
        mock_http.post.assert_awaited_once_with(
            "/v1/query",
            json={"query": "q", "namespace": "default", "top_k": 5},
            headers={"X-Tenant-ID": "default"},
        )

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(
            side_effect=Exception("Connection refused")
        )
        result = await client.query("test")
        assert "error" in result
        assert "Connection refused" in result["error"]
        assert result["results"] == []

    async def test_raise_for_status_called(self):
        client = RAGClient("http://test:8070")
        resp = _mock_response({"results": []})
        mock_http = AsyncMock()
        mock_http.post.return_value = resp
        client._client = mock_http
        await client.query("q")
        resp.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# query() — Vertex AI adapter
# ---------------------------------------------------------------------------


class TestQueryVertex:
    async def test_delegates_to_vertex_adapter(self):
        mock_adapter = AsyncMock()
        mock_adapter.search.return_value = {"results": [{"text": "vertex result"}]}
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)

        result = await client.query("test query", tenant_id="t1", top_k=3)

        assert result == {"results": [{"text": "vertex result"}]}
        mock_adapter.search.assert_awaited_once_with(
            query="test query", tenant_id="t1", top_k=3
        )


# ---------------------------------------------------------------------------
# upload_document() — HTTP fallback
# ---------------------------------------------------------------------------


class TestUploadDocumentHTTP:
    async def test_success(self):
        client, mock_http = _make_client_with_mock_http({"doc_id": "abc"})
        result = await client.upload_document(
            "content text", {"type": "note"}, tenant_id="t1"
        )
        assert result == {"doc_id": "abc"}
        mock_http.post.assert_awaited_once_with(
            "/v1/upload",
            json={
                "content": "content text",
                "metadata": {"type": "note"},
                "namespace": "t1",
            },
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_default_tenant(self):
        client, mock_http = _make_client_with_mock_http({"doc_id": "x"})
        await client.upload_document("c", {})
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[1]["json"]["namespace"] == "default"
        assert call_kwargs[1]["headers"]["X-Tenant-ID"] == "default"

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("Upload failed"))
        result = await client.upload_document("text", {})
        assert "error" in result
        assert "Upload failed" in result["error"]

    async def test_raise_for_status_called(self):
        client = RAGClient("http://test:8070")
        resp = _mock_response({})
        mock_http = AsyncMock()
        mock_http.post.return_value = resp
        client._client = mock_http
        await client.upload_document("c", {})
        resp.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# upload_document() — Vertex AI adapter
# ---------------------------------------------------------------------------


class TestUploadDocumentVertex:
    async def test_delegates_to_vertex_adapter(self):
        mock_adapter = AsyncMock()
        mock_adapter.upsert_document.return_value = {
            "status": "completed",
            "document_id": "odoo-sale_order-42",
        }
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)

        result = await client.upload_document(
            content={"document_type": "odoo_sale_order", "extracted_text": "SO42"},
            metadata={"source": "odoo", "model": "sale.order", "record_id": 42},
            tenant_id="t1",
            doc_id="odoo-sale_order-42",
        )

        assert result["status"] == "completed"
        mock_adapter.upsert_document.assert_awaited_once()

    async def test_generates_doc_id_from_metadata(self):
        mock_adapter = AsyncMock()
        mock_adapter.upsert_document.return_value = {"status": "completed"}
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)

        await client.upload_document(
            content="text content",
            metadata={"source": "odoo", "model": "sale.order", "record_id": 42},
            tenant_id="t1",
        )

        call_kwargs = mock_adapter.upsert_document.call_args.kwargs
        assert call_kwargs["document_id"] == "odoo-sale_order-42"


# ---------------------------------------------------------------------------
# list_documents()
# ---------------------------------------------------------------------------


class TestListDocuments:
    async def test_http_success(self):
        client, mock_http = _make_client_with_mock_http({"documents": [{"id": "d1"}]})
        result = await client.list_documents(tenant_id="t1")
        assert result == {"documents": [{"id": "d1"}]}
        mock_http.get.assert_awaited_once_with(
            "/v1/documents",
            params={"namespace": "t1"},
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_vertex_returns_unsupported(self):
        mock_adapter = AsyncMock()
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)
        result = await client.list_documents(tenant_id="t1")
        assert result["documents"] == []

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("List failed"))
        result = await client.list_documents()
        assert "error" in result
        assert result["documents"] == []


# ---------------------------------------------------------------------------
# get_document()
# ---------------------------------------------------------------------------


class TestGetDocument:
    async def test_http_success(self):
        client, mock_http = _make_client_with_mock_http(
            {"id": "d1", "content": "doc body"}
        )
        result = await client.get_document("d1", tenant_id="t1")
        assert result == {"id": "d1", "content": "doc body"}
        mock_http.get.assert_awaited_once_with(
            "/v1/documents/d1",
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_vertex_delegates(self):
        mock_adapter = AsyncMock()
        mock_adapter.get_document.return_value = {"id": "d1", "mock": True}
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)

        result = await client.get_document("d1", tenant_id="t1")
        assert result["id"] == "d1"
        mock_adapter.get_document.assert_awaited_once_with(
            document_id="d1", tenant_id="t1"
        )

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("Not found"))
        result = await client.get_document("d1")
        assert "error" in result


# ---------------------------------------------------------------------------
# delete_document()
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    async def test_http_success(self):
        client, mock_http = _make_client_with_mock_http({"deleted": True})
        result = await client.delete_document("d1", tenant_id="t1")
        assert result == {"deleted": True}
        mock_http.delete.assert_awaited_once_with(
            "/v1/documents/d1",
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_vertex_delegates(self):
        mock_adapter = AsyncMock()
        mock_adapter.delete_document.return_value = {"status": "completed"}
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)

        result = await client.delete_document("d1", tenant_id="t1")
        assert result["status"] == "completed"
        mock_adapter.delete_document.assert_awaited_once_with(
            document_id="d1", tenant_id="t1"
        )

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("Delete failed"))
        result = await client.delete_document("d1")
        assert "error" in result


# ---------------------------------------------------------------------------
# get_context() — delegates to query()
# ---------------------------------------------------------------------------


class TestGetContext:
    async def test_delegates_to_query(self):
        client, mock_http = _make_client_with_mock_http(
            {"results": [{"text": "context data"}]}
        )
        result = await client.get_context("res.partner", 42, tenant_id="t1")
        assert result == {"results": [{"text": "context data"}]}
        mock_http.post.assert_awaited_once_with(
            "/v1/query",
            json={
                "query": "res.partner record 42",
                "namespace": "t1",
                "top_k": 5,
            },
            headers={"X-Tenant-ID": "t1"},
        )


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------


class TestGetStats:
    async def test_http_success(self):
        client, mock_http = _make_client_with_mock_http(
            {"total_docs": 100, "index_size": "50MB"}
        )
        result = await client.get_stats(tenant_id="t1")
        assert result == {"total_docs": 100, "index_size": "50MB"}
        mock_http.get.assert_awaited_once_with(
            "/v1/stats",
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_vertex_returns_backend_info(self):
        mock_adapter = AsyncMock()
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)
        result = await client.get_stats(tenant_id="t1")
        assert result["backend"] == "vertex_ai"

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("Stats failed"))
        result = await client.get_stats()
        assert "error" in result


# ---------------------------------------------------------------------------
# _generate_doc_id
# ---------------------------------------------------------------------------


class TestGenerateDocId:
    def test_odoo_source(self):
        doc_id = RAGClient._generate_doc_id(
            {
                "source": "odoo",
                "model": "sale.order",
                "record_id": 42,
            }
        )
        assert doc_id == "odoo-sale_order-42"

    def test_fallback_hash(self):
        doc_id = RAGClient._generate_doc_id({"source": "manual", "title": "doc"})
        assert doc_id.startswith("manual-")
        assert len(doc_id) > len("manual-")


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestRAGClientInit:
    def test_base_url_strips_trailing_slash(self):
        client = RAGClient("http://test:8070/")
        assert client.base_url == "http://test:8070"

    def test_base_url_preserved_without_slash(self):
        client = RAGClient("http://test:8070")
        assert client.base_url == "http://test:8070"

    def test_client_starts_as_none(self):
        client = RAGClient("http://test:8070")
        assert client._client is None

    def test_vertex_adapter_stored(self):
        mock_adapter = AsyncMock()
        client = RAGClient("http://test:8070", vertex_adapter=mock_adapter)
        assert client.vertex_adapter is mock_adapter

    def test_no_vertex_adapter_by_default(self):
        client = RAGClient("http://test:8070")
        assert client.vertex_adapter is None
