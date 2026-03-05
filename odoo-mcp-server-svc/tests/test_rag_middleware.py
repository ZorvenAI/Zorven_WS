"""Tests for RAG context middleware — enriches tool calls with knowledge context."""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.rag.middleware import RAGContextMiddleware

# ── Fixtures ──


@pytest.fixture
def mock_rag_client() -> AsyncMock:
    """Mock RAG client with standard query response."""
    client = AsyncMock()
    client.query.return_value = {
        "results": [
            {"text": "Product A is a best-seller in Q4."},
            {"text": "Sales policy allows 10% discount."},
            {"text": "Partner XYZ is a premium customer."},
        ]
    }
    return client


@pytest.fixture
def middleware(mock_rag_client: AsyncMock) -> RAGContextMiddleware:
    """Middleware with mocked RAG client and RAG_ENABLED=True."""
    return RAGContextMiddleware(rag_client=mock_rag_client)


@pytest.fixture
def middleware_no_client() -> RAGContextMiddleware:
    """Middleware without a RAG client."""
    return RAGContextMiddleware(rag_client=None)


# ── Constructor tests ──


class TestMiddlewareInit:
    """Test RAGContextMiddleware initialization."""

    def test_init_with_client(self, mock_rag_client: AsyncMock) -> None:
        mw = RAGContextMiddleware(rag_client=mock_rag_client)
        assert mw.rag_client is mock_rag_client

    def test_init_without_client(self) -> None:
        mw = RAGContextMiddleware()
        assert mw.rag_client is None

    def test_init_explicit_none(self) -> None:
        mw = RAGContextMiddleware(rag_client=None)
        assert mw.rag_client is None


# ── Enrichment with RAG enabled ──


class TestEnrichWithRAGEnabled:
    """Test enrich() when RAG_ENABLED=True and a client is present."""

    @patch("app.rag.middleware.settings")
    async def test_injects_background_context(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
    ) -> None:
        """Enrich injects background_context when RAG returns results."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        arguments = {"model": "res.partner", "name": "Acme Corp"}
        context = {"tenant_id": "tenant-1"}

        result = await middleware.enrich("search_partner", arguments, context)

        assert "background_context" in result
        assert "Product A" in result["background_context"]
        assert "Sales policy" in result["background_context"]

    @patch("app.rag.middleware.settings")
    async def test_preserves_existing_arguments(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
    ) -> None:
        """Enrich preserves original arguments alongside background_context."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        arguments = {"model": "sale.order", "query": "recent orders"}
        context = {"tenant_id": "default"}

        result = await middleware.enrich("search_orders", arguments, context)

        assert result["model"] == "sale.order"
        assert result["query"] == "recent orders"
        assert "background_context" in result

    @patch("app.rag.middleware.settings")
    async def test_passes_tenant_id_to_query(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Enrich passes the correct tenant_id to rag_client.query()."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        arguments = {"query": "inventory levels"}
        context = {"tenant_id": "acme-corp"}

        await middleware.enrich("check_inventory", arguments, context)

        mock_rag_client.query.assert_awaited_once()
        call_kwargs = mock_rag_client.query.call_args
        assert call_kwargs.kwargs["tenant_id"] == "acme-corp"
        assert call_kwargs.kwargs["top_k"] == 3

    @patch("app.rag.middleware.settings")
    async def test_truncates_context_to_max_tokens(
        self,
        mock_settings: AsyncMock,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Enrich truncates background_context based on RAG_CONTEXT_MAX_TOKENS."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 10  # 10 tokens * 4 chars = 40 chars

        # Return a very long result
        long_text = "A" * 500
        mock_rag_client.query.return_value = {"results": [{"text": long_text}]}

        mw = RAGContextMiddleware(rag_client=mock_rag_client)
        arguments = {"query": "test"}
        context = {"tenant_id": "default"}

        result = await mw.enrich("test_tool", arguments, context)

        assert "background_context" in result
        assert len(result["background_context"]) <= 40

    @patch("app.rag.middleware.settings")
    async def test_builds_query_from_multiple_keys(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Enrich builds the semantic query from model, name, query keys."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        arguments = {
            "model": "crm.lead",
            "name": "New Deal",
            "search_term": "lead pipeline",
        }
        context = {"tenant_id": "default"}

        await middleware.enrich("search_leads", arguments, context)

        call_kwargs = mock_rag_client.query.call_args
        query = call_kwargs.kwargs["query"]
        assert "crm.lead" in query
        assert "New Deal" in query
        assert "lead pipeline" in query

    @patch("app.rag.middleware.settings")
    async def test_query_limited_to_500_chars(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Semantic query is capped at 500 characters."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        arguments = {"query": "X" * 600}
        context = {"tenant_id": "default"}

        await middleware.enrich("long_query_tool", arguments, context)

        call_kwargs = mock_rag_client.query.call_args
        query = call_kwargs.kwargs["query"]
        assert len(query) <= 500

    @patch("app.rag.middleware.settings")
    async def test_uses_content_key_from_results(
        self,
        mock_settings: AsyncMock,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Enrich falls back to 'content' key if 'text' is missing."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        mock_rag_client.query.return_value = {
            "results": [{"content": "Fallback content from RAG"}]
        }

        mw = RAGContextMiddleware(rag_client=mock_rag_client)
        arguments = {"query": "test"}
        context = {"tenant_id": "default"}

        result = await mw.enrich("test_tool", arguments, context)

        assert "Fallback content" in result["background_context"]

    @patch("app.rag.middleware.settings")
    async def test_limits_results_to_3(
        self,
        mock_settings: AsyncMock,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Enrich only uses top 3 results even if more are returned."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 5000
        mock_rag_client.query.return_value = {
            "results": [{"text": f"Result {i}"} for i in range(10)]
        }

        mw = RAGContextMiddleware(rag_client=mock_rag_client)
        arguments = {"query": "many results"}
        context = {"tenant_id": "default"}

        result = await mw.enrich("test_tool", arguments, context)

        bg_ctx = result["background_context"]
        assert "Result 0" in bg_ctx
        assert "Result 1" in bg_ctx
        assert "Result 2" in bg_ctx
        # Results beyond top 3 should not appear
        assert "Result 3" not in bg_ctx


# ── No enrichment scenarios ──


class TestEnrichSkipped:
    """Test scenarios where enrichment is skipped."""

    @patch("app.rag.middleware.settings")
    async def test_skipped_when_rag_disabled(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
    ) -> None:
        """Returns unmodified arguments when RAG_ENABLED=False."""
        mock_settings.RAG_ENABLED = False
        arguments = {"model": "res.partner"}
        context = {"tenant_id": "default"}

        result = await middleware.enrich("search", arguments, context)

        assert "background_context" not in result
        assert result == arguments

    @patch("app.rag.middleware.settings")
    async def test_skipped_when_no_client(
        self,
        mock_settings: AsyncMock,
        middleware_no_client: RAGContextMiddleware,
    ) -> None:
        """Returns unmodified arguments when rag_client is None."""
        mock_settings.RAG_ENABLED = True
        arguments = {"model": "res.partner"}
        context = {"tenant_id": "default"}

        result = await middleware_no_client.enrich("search", arguments, context)

        assert "background_context" not in result

    @patch("app.rag.middleware.settings")
    async def test_skipped_when_no_query_parts(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Returns unmodified arguments when no recognized keys are present."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        arguments = {"limit": 10, "offset": 0}
        context = {"tenant_id": "default"}

        result = await middleware.enrich("generic_tool", arguments, context)

        assert "background_context" not in result
        mock_rag_client.query.assert_not_awaited()

    @patch("app.rag.middleware.settings")
    async def test_skipped_when_results_empty(
        self,
        mock_settings: AsyncMock,
        mock_rag_client: AsyncMock,
    ) -> None:
        """No background_context injected when query returns empty results."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        mock_rag_client.query.return_value = {"results": []}

        mw = RAGContextMiddleware(rag_client=mock_rag_client)
        arguments = {"query": "nothing matches"}
        context = {"tenant_id": "default"}

        result = await mw.enrich("search_tool", arguments, context)

        assert "background_context" not in result

    @patch("app.rag.middleware.settings")
    async def test_default_tenant_id_when_missing(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Uses 'default' tenant_id when context lacks it."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        arguments = {"query": "test"}
        context = {}  # No tenant_id

        await middleware.enrich("test_tool", arguments, context)

        call_kwargs = mock_rag_client.query.call_args
        assert call_kwargs.kwargs["tenant_id"] == "default"


# ── Error handling ──


class TestEnrichErrorHandling:
    """Test graceful error handling during enrichment."""

    @patch("app.rag.middleware.settings")
    async def test_handles_rag_client_exception(
        self,
        mock_settings: AsyncMock,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Returns unmodified arguments when rag_client.query() raises."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        mock_rag_client.query.side_effect = Exception("Connection refused")

        mw = RAGContextMiddleware(rag_client=mock_rag_client)
        arguments = {"query": "test"}
        context = {"tenant_id": "default"}

        result = await mw.enrich("test_tool", arguments, context)

        assert "background_context" not in result
        # Original arguments still intact
        assert result["query"] == "test"

    @patch("app.rag.middleware.settings")
    async def test_logs_warning_on_exception(
        self,
        mock_settings: AsyncMock,
        mock_rag_client: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Logs a warning when enrichment fails."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        mock_rag_client.query.side_effect = TimeoutError("Timeout")

        mw = RAGContextMiddleware(rag_client=mock_rag_client)
        arguments = {"query": "test"}
        context = {"tenant_id": "default"}

        with caplog.at_level(logging.WARNING):
            await mw.enrich("test_tool", arguments, context)

        assert "RAG context enrichment failed" in caplog.text

    @patch("app.rag.middleware.settings")
    async def test_handles_malformed_rag_response(
        self,
        mock_settings: AsyncMock,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Handles a response missing the 'results' key gracefully."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        mock_rag_client.query.return_value = {"error": "internal error"}

        mw = RAGContextMiddleware(rag_client=mock_rag_client)
        arguments = {"query": "test"}
        context = {"tenant_id": "default"}

        result = await mw.enrich("test_tool", arguments, context)

        # No crash, no background_context
        assert "background_context" not in result


# ── Logging ──


class TestEnrichLogging:
    """Test that successful enrichment is logged."""

    @patch("app.rag.middleware.settings")
    async def test_logs_info_on_success(
        self,
        mock_settings: AsyncMock,
        middleware: RAGContextMiddleware,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Logs an info message with tool name and char count on success."""
        mock_settings.RAG_ENABLED = True
        mock_settings.RAG_CONTEXT_MAX_TOKENS = 2000
        arguments = {"query": "test query"}
        context = {"tenant_id": "default"}

        with caplog.at_level(logging.INFO):
            await middleware.enrich("search_partners", arguments, context)

        assert "RAG context injected" in caplog.text
        assert "search_partners" in caplog.text
