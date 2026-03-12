"""Tests for SKL-CIA-07: RAG Context Retrieval."""

from unittest.mock import AsyncMock, patch

from app.skills.rag_context_retrieval import RAGContextRetrieval
from app.skills.models import SkillContext


def _context():
    return SkillContext(session_id="s1", tenant_id="t1")


class TestRAGContextRetrieval:
    async def test_meta_skill_id(self):
        skill = RAGContextRetrieval(rag_enabled=False)
        assert skill.meta.skill_id == "SKL-CIA-07"

    async def test_disabled_returns_empty(self):
        skill = RAGContextRetrieval(rag_enabled=False)
        result = await skill.execute({"query": "competitors"}, _context())
        assert result.success
        assert result.data["chunks"] == []
        assert result.data["rag_enabled"] is False

    async def test_no_query_returns_error(self):
        skill = RAGContextRetrieval(rag_enabled=True)
        result = await skill.execute({"query": ""}, _context())
        assert not result.success
        assert "No query" in result.error

    @patch("app.skills.rag_context_retrieval.httpx.AsyncClient")
    async def test_retrieves_chunks_when_enabled(self, mock_client_cls):
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "chunks": [
                {"content": "Previous competitor analysis for AI tools", "score": 0.9},
                {"content": "SWOT for Acme Corp from Q1 2025", "score": 0.8},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        skill = RAGContextRetrieval(
            rag_service_url="http://rag:8070",
            rag_enabled=True,
        )
        result = await skill.execute({"query": "competitor analysis"}, _context())
        assert result.success
        assert result.data["chunk_count"] == 2
        assert result.data["rag_enabled"] is True

    @patch("app.skills.rag_context_retrieval.httpx.AsyncClient")
    async def test_handles_rag_failure(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("RAG service down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        skill = RAGContextRetrieval(
            rag_service_url="http://rag:8070",
            rag_enabled=True,
        )
        result = await skill.execute({"query": "competitors"}, _context())
        assert not result.success
        assert "RAG service down" in result.error
