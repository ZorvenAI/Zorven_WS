"""Tests for RAG tools — full coverage of all 8 tools."""

from unittest.mock import AsyncMock

from app.tools.rag.tools import (
    ALL_RAG_TOOLS,
    DeleteDocumentTool,
    EnrichContextTool,
    GetStoreStatsTool,
    IndexOdooRecordTool,
    ListDocumentsTool,
    QueryKnowledgeTool,
    SearchByMetadataTool,
    UploadDocumentTool,
)

# ---------------------------------------------------------------------------
# ALL_RAG_TOOLS collection
# ---------------------------------------------------------------------------


class TestAllRagTools:
    def test_count(self):
        assert len(ALL_RAG_TOOLS) == 8

    def test_all_tools_have_rag_domain(self):
        for tool in ALL_RAG_TOOLS:
            assert tool.domain == "rag"

    def test_all_tools_have_names(self):
        for tool in ALL_RAG_TOOLS:
            assert tool.name.startswith("rag_")

    def test_all_tools_have_descriptions(self):
        for tool in ALL_RAG_TOOLS:
            assert len(tool.description) > 0

    def test_all_tools_have_input_schema(self):
        for tool in ALL_RAG_TOOLS:
            assert isinstance(tool.input_schema, dict)

    def test_unique_names(self):
        names = [t.name for t in ALL_RAG_TOOLS]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# QueryKnowledgeTool
# ---------------------------------------------------------------------------


class TestQueryKnowledgeTool:
    async def test_no_client_returns_error(self):
        tool = QueryKnowledgeTool()
        result = await tool.execute({"query": "test"})
        assert result == {"error": "RAG client not available", "results": []}

    async def test_no_client_with_none_context(self):
        tool = QueryKnowledgeTool()
        result = await tool.execute({"query": "test"}, context=None)
        assert "error" in result
        assert result["results"] == []

    async def test_no_client_with_empty_context(self):
        tool = QueryKnowledgeTool()
        result = await tool.execute({"query": "test"}, context={})
        assert "error" in result

    async def test_with_client(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": [{"text": "answer"}]}
        tool = QueryKnowledgeTool()
        result = await tool.execute(
            {"query": "test"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        assert result == {"results": [{"text": "answer"}]}
        rag.query.assert_awaited_once_with("test", tenant_id="t1", top_k=5)

    async def test_with_client_custom_top_k(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": []}
        tool = QueryKnowledgeTool()
        result = await tool.execute(
            {"query": "test", "top_k": 10},
            {"rag_client": rag, "tenant_id": "t2"},
        )
        rag.query.assert_awaited_once_with("test", tenant_id="t2", top_k=10)
        assert result == {"results": []}

    async def test_with_client_default_tenant(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": []}
        tool = QueryKnowledgeTool()
        await tool.execute({"query": "q"}, {"rag_client": rag})
        rag.query.assert_awaited_once_with("q", tenant_id="default", top_k=5)


# ---------------------------------------------------------------------------
# UploadDocumentTool
# ---------------------------------------------------------------------------


class TestUploadDocumentTool:
    async def test_no_client_returns_error(self):
        tool = UploadDocumentTool()
        result = await tool.execute({"content": "doc text"})
        assert result == {"error": "RAG client not available"}

    async def test_no_client_with_none_context(self):
        tool = UploadDocumentTool()
        result = await tool.execute({"content": "doc"}, context=None)
        assert "error" in result

    async def test_with_client(self):
        rag = AsyncMock()
        rag.upload_document.return_value = {"doc_id": "abc123"}
        tool = UploadDocumentTool()
        result = await tool.execute(
            {"content": "hello", "metadata": {"type": "note"}},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        assert result == {"doc_id": "abc123"}
        rag.upload_document.assert_awaited_once_with(
            "hello", {"type": "note"}, tenant_id="t1"
        )

    async def test_with_client_default_metadata(self):
        rag = AsyncMock()
        rag.upload_document.return_value = {"doc_id": "xyz"}
        tool = UploadDocumentTool()
        await tool.execute(
            {"content": "text"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        rag.upload_document.assert_awaited_once_with("text", {}, tenant_id="t1")

    async def test_with_client_default_tenant(self):
        rag = AsyncMock()
        rag.upload_document.return_value = {}
        tool = UploadDocumentTool()
        await tool.execute({"content": "c"}, {"rag_client": rag})
        rag.upload_document.assert_awaited_once_with("c", {}, tenant_id="default")


# ---------------------------------------------------------------------------
# ListDocumentsTool
# ---------------------------------------------------------------------------


class TestListDocumentsTool:
    async def test_no_client_returns_error(self):
        tool = ListDocumentsTool()
        result = await tool.execute({})
        assert result == {"error": "RAG client not available", "documents": []}

    async def test_no_client_with_none_context(self):
        tool = ListDocumentsTool()
        result = await tool.execute({}, context=None)
        assert "error" in result
        assert result["documents"] == []

    async def test_with_client(self):
        rag = AsyncMock()
        rag.list_documents.return_value = {"documents": [{"id": "d1"}, {"id": "d2"}]}
        tool = ListDocumentsTool()
        result = await tool.execute({}, {"rag_client": rag, "tenant_id": "t1"})
        assert len(result["documents"]) == 2
        rag.list_documents.assert_awaited_once_with(tenant_id="t1")

    async def test_with_client_default_tenant(self):
        rag = AsyncMock()
        rag.list_documents.return_value = {"documents": []}
        tool = ListDocumentsTool()
        await tool.execute({}, {"rag_client": rag})
        rag.list_documents.assert_awaited_once_with(tenant_id="default")


# ---------------------------------------------------------------------------
# DeleteDocumentTool
# ---------------------------------------------------------------------------


class TestDeleteDocumentTool:
    async def test_no_client_returns_error(self):
        tool = DeleteDocumentTool()
        result = await tool.execute({"doc_id": "d1"})
        assert result == {"error": "RAG client not available"}

    async def test_no_client_with_none_context(self):
        tool = DeleteDocumentTool()
        result = await tool.execute({"doc_id": "d1"}, context=None)
        assert "error" in result

    async def test_with_client(self):
        rag = AsyncMock()
        rag.delete_document.return_value = {"deleted": True}
        tool = DeleteDocumentTool()
        result = await tool.execute(
            {"doc_id": "d1"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        assert result == {"deleted": True}
        rag.delete_document.assert_awaited_once_with("d1", tenant_id="t1")

    async def test_with_client_default_tenant(self):
        rag = AsyncMock()
        rag.delete_document.return_value = {}
        tool = DeleteDocumentTool()
        await tool.execute({"doc_id": "x"}, {"rag_client": rag})
        rag.delete_document.assert_awaited_once_with("x", tenant_id="default")


# ---------------------------------------------------------------------------
# EnrichContextTool
# ---------------------------------------------------------------------------


class TestEnrichContextTool:
    async def test_no_client_returns_error(self):
        tool = EnrichContextTool()
        result = await tool.execute({"query": "test"})
        assert result == {"error": "RAG client not available"}

    async def test_no_client_with_none_context(self):
        tool = EnrichContextTool()
        result = await tool.execute({"query": "q"}, context=None)
        assert "error" in result

    async def test_with_client_builds_context(self):
        rag = AsyncMock()
        rag.query.return_value = {
            "results": [
                {"text": "first"},
                {"text": "second"},
                {"content": "third"},
            ]
        }
        tool = EnrichContextTool()
        result = await tool.execute(
            {"query": "test"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        assert result["sources"] == 3
        assert "first" in result["context"]
        assert "second" in result["context"]
        assert "third" in result["context"]
        assert result["context"] == "first\n\nsecond\n\nthird"
        rag.query.assert_awaited_once_with("test", tenant_id="t1", top_k=3)

    async def test_with_client_empty_results(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": []}
        tool = EnrichContextTool()
        result = await tool.execute(
            {"query": "nothing"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        assert result == {"context": "", "sources": 0}

    async def test_with_client_truncates_to_3(self):
        """Only first 3 results are included in context text."""
        rag = AsyncMock()
        rag.query.return_value = {
            "results": [
                {"text": "a"},
                {"text": "b"},
                {"text": "c"},
                {"text": "d"},
                {"text": "e"},
            ]
        }
        tool = EnrichContextTool()
        result = await tool.execute(
            {"query": "q"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        # sources counts ALL results returned, context only uses first 3
        assert result["sources"] == 5
        assert result["context"] == "a\n\nb\n\nc"

    async def test_with_client_uses_content_fallback(self):
        """When 'text' key is absent, falls back to 'content' key."""
        rag = AsyncMock()
        rag.query.return_value = {"results": [{"content": "fallback_value"}]}
        tool = EnrichContextTool()
        result = await tool.execute(
            {"query": "q"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        assert result["context"] == "fallback_value"

    async def test_with_client_default_tenant(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": []}
        tool = EnrichContextTool()
        await tool.execute({"query": "q"}, {"rag_client": rag})
        rag.query.assert_awaited_once_with("q", tenant_id="default", top_k=3)

    async def test_with_client_missing_results_key(self):
        """When query returns dict without 'results' key."""
        rag = AsyncMock()
        rag.query.return_value = {}
        tool = EnrichContextTool()
        result = await tool.execute(
            {"query": "q"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        assert result == {"context": "", "sources": 0}


# ---------------------------------------------------------------------------
# IndexOdooRecordTool
# ---------------------------------------------------------------------------


class TestIndexOdooRecordTool:
    async def test_no_sync_returns_error(self):
        tool = IndexOdooRecordTool()
        result = await tool.execute({"model": "res.partner", "record_id": 1})
        assert result == {"error": "RAG sync not available"}

    async def test_no_sync_with_none_context(self):
        tool = IndexOdooRecordTool()
        result = await tool.execute(
            {"model": "res.partner", "record_id": 1}, context=None
        )
        assert "error" in result

    async def test_with_sync(self):
        rag_sync = AsyncMock()
        rag_sync.sync_record.return_value = {"indexed": True}
        tool = IndexOdooRecordTool()
        result = await tool.execute(
            {"model": "res.partner", "record_id": 42},
            {"rag_sync": rag_sync, "tenant_id": "t1"},
        )
        assert result == {"indexed": True}
        rag_sync.sync_record.assert_awaited_once_with("res.partner", 42, "t1")

    async def test_with_sync_default_tenant(self):
        rag_sync = AsyncMock()
        rag_sync.sync_record.return_value = {}
        tool = IndexOdooRecordTool()
        await tool.execute(
            {"model": "sale.order", "record_id": 7},
            {"rag_sync": rag_sync},
        )
        rag_sync.sync_record.assert_awaited_once_with("sale.order", 7, "default")


# ---------------------------------------------------------------------------
# SearchByMetadataTool
# ---------------------------------------------------------------------------


class TestSearchByMetadataTool:
    async def test_no_client_returns_error(self):
        tool = SearchByMetadataTool()
        result = await tool.execute({"model": "res.partner"})
        assert result == {"error": "RAG client not available", "results": []}

    async def test_no_client_with_none_context(self):
        tool = SearchByMetadataTool()
        result = await tool.execute({"model": "res.partner"}, context=None)
        assert "error" in result
        assert result["results"] == []

    async def test_with_client(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": [{"id": "r1"}]}
        tool = SearchByMetadataTool()
        result = await tool.execute(
            {"model": "res.partner", "query": "active customers"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        assert result == {"results": [{"id": "r1"}]}
        rag.query.assert_awaited_once_with(
            "model:res.partner active customers", tenant_id="t1", top_k=10
        )

    async def test_with_client_no_query(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": []}
        tool = SearchByMetadataTool()
        await tool.execute(
            {"model": "sale.order"},
            {"rag_client": rag, "tenant_id": "t1"},
        )
        rag.query.assert_awaited_once_with(
            "model:sale.order ", tenant_id="t1", top_k=10
        )

    async def test_with_client_default_tenant(self):
        rag = AsyncMock()
        rag.query.return_value = {"results": []}
        tool = SearchByMetadataTool()
        await tool.execute({"model": "m"}, {"rag_client": rag})
        rag.query.assert_awaited_once_with("model:m ", tenant_id="default", top_k=10)


# ---------------------------------------------------------------------------
# GetStoreStatsTool
# ---------------------------------------------------------------------------


class TestGetStoreStatsTool:
    async def test_no_client_returns_error(self):
        tool = GetStoreStatsTool()
        result = await tool.execute({})
        assert result == {"error": "RAG client not available"}

    async def test_no_client_with_none_context(self):
        tool = GetStoreStatsTool()
        result = await tool.execute({}, context=None)
        assert "error" in result

    async def test_with_client(self):
        rag = AsyncMock()
        rag.get_stats.return_value = {"total_docs": 42, "index_size": "10MB"}
        tool = GetStoreStatsTool()
        result = await tool.execute({}, {"rag_client": rag, "tenant_id": "t1"})
        assert result == {"total_docs": 42, "index_size": "10MB"}
        rag.get_stats.assert_awaited_once_with(tenant_id="t1")

    async def test_with_client_default_tenant(self):
        rag = AsyncMock()
        rag.get_stats.return_value = {}
        tool = GetStoreStatsTool()
        await tool.execute({}, {"rag_client": rag})
        rag.get_stats.assert_awaited_once_with(tenant_id="default")
