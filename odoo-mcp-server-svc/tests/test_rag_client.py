"""Tests for RAG client — full coverage of all HTTP methods."""

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
    """Create a RAGClient with a pre-injected mock HTTP client.

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
# query()
# ---------------------------------------------------------------------------


class TestQuery:
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
# upload_document()
# ---------------------------------------------------------------------------


class TestUploadDocument:
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
# list_documents()
# ---------------------------------------------------------------------------


class TestListDocuments:
    async def test_success(self):
        client, mock_http = _make_client_with_mock_http({"documents": [{"id": "d1"}]})
        result = await client.list_documents(tenant_id="t1")
        assert result == {"documents": [{"id": "d1"}]}
        mock_http.get.assert_awaited_once_with(
            "/v1/documents",
            params={"namespace": "t1"},
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_default_tenant(self):
        client, mock_http = _make_client_with_mock_http({"documents": []})
        await client.list_documents()
        call_kwargs = mock_http.get.call_args
        assert call_kwargs[1]["params"]["namespace"] == "default"

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("List failed"))
        result = await client.list_documents()
        assert "error" in result
        assert result["documents"] == []

    async def test_raise_for_status_called(self):
        client = RAGClient("http://test:8070")
        resp = _mock_response({"documents": []})
        mock_http = AsyncMock()
        mock_http.get.return_value = resp
        client._client = mock_http
        await client.list_documents()
        resp.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# get_document()
# ---------------------------------------------------------------------------


class TestGetDocument:
    async def test_success(self):
        client, mock_http = _make_client_with_mock_http(
            {"id": "d1", "content": "doc body"}
        )
        result = await client.get_document("d1", tenant_id="t1")
        assert result == {"id": "d1", "content": "doc body"}
        mock_http.get.assert_awaited_once_with(
            "/v1/documents/d1",
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_default_tenant(self):
        client, mock_http = _make_client_with_mock_http({"id": "d1"})
        await client.get_document("d1")
        mock_http.get.assert_awaited_once_with(
            "/v1/documents/d1",
            headers={"X-Tenant-ID": "default"},
        )

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("Not found"))
        result = await client.get_document("d1")
        assert "error" in result
        assert "Not found" in result["error"]

    async def test_raise_for_status_called(self):
        client = RAGClient("http://test:8070")
        resp = _mock_response({"id": "d1"})
        mock_http = AsyncMock()
        mock_http.get.return_value = resp
        client._client = mock_http
        await client.get_document("d1")
        resp.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# delete_document()
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    async def test_success(self):
        client, mock_http = _make_client_with_mock_http({"deleted": True})
        result = await client.delete_document("d1", tenant_id="t1")
        assert result == {"deleted": True}
        mock_http.delete.assert_awaited_once_with(
            "/v1/documents/d1",
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_default_tenant(self):
        client, mock_http = _make_client_with_mock_http({"deleted": True})
        await client.delete_document("d1")
        mock_http.delete.assert_awaited_once_with(
            "/v1/documents/d1",
            headers={"X-Tenant-ID": "default"},
        )

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("Delete failed"))
        result = await client.delete_document("d1")
        assert "error" in result
        assert "Delete failed" in result["error"]

    async def test_raise_for_status_called(self):
        client = RAGClient("http://test:8070")
        resp = _mock_response({})
        mock_http = AsyncMock()
        mock_http.delete.return_value = resp
        client._client = mock_http
        await client.delete_document("d1")
        resp.raise_for_status.assert_called_once()


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

    async def test_default_tenant(self):
        client, mock_http = _make_client_with_mock_http({"results": []})
        await client.get_context("sale.order", 1)
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[1]["json"]["namespace"] == "default"

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("Query failed"))
        result = await client.get_context("res.partner", 1)
        assert "error" in result


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------


class TestGetStats:
    async def test_success(self):
        client, mock_http = _make_client_with_mock_http(
            {"total_docs": 100, "index_size": "50MB"}
        )
        result = await client.get_stats(tenant_id="t1")
        assert result == {"total_docs": 100, "index_size": "50MB"}
        mock_http.get.assert_awaited_once_with(
            "/v1/stats",
            headers={"X-Tenant-ID": "t1"},
        )

    async def test_default_tenant(self):
        client, mock_http = _make_client_with_mock_http({"total_docs": 0})
        await client.get_stats()
        mock_http.get.assert_awaited_once_with(
            "/v1/stats",
            headers={"X-Tenant-ID": "default"},
        )

    async def test_exception_returns_error(self):
        client, _ = _make_client_with_mock_http(side_effect=Exception("Stats failed"))
        result = await client.get_stats()
        assert "error" in result
        assert "Stats failed" in result["error"]

    async def test_raise_for_status_called(self):
        client = RAGClient("http://test:8070")
        resp = _mock_response({"total_docs": 0})
        mock_http = AsyncMock()
        mock_http.get.return_value = resp
        client._client = mock_http
        await client.get_stats()
        resp.raise_for_status.assert_called_once()


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
