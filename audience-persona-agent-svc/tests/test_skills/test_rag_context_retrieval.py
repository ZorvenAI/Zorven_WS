"""Tests for SKL-APA-06: RAG Context Retrieval."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.skills.rag_context_retrieval import RAGContextRetrieval
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


class TestRAGContextRetrieval:
    async def test_meta(self):
        skill = RAGContextRetrieval()
        assert skill.meta.skill_id == "SKL-APA-06"
        assert skill.meta.circuit_breaker_dependency == "rag_store"

    async def test_rag_disabled(self):
        skill = RAGContextRetrieval(rag_enabled=False)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is True
        assert result.data["rag_enabled"] is False
        assert result.data["chunks"] == []

    async def test_empty_prompt(self):
        skill = RAGContextRetrieval(rag_enabled=True)
        result = await skill.execute({"prompt": ""}, _ctx())
        assert result.success is False

    @patch("app.skills.rag_context_retrieval.httpx.AsyncClient")
    async def test_rag_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "chunks": [{"content": "Prior persona data", "metadata": {}, "score": 0.9}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        skill = RAGContextRetrieval(
            rag_service_url="http://localhost:8070", rag_enabled=True
        )
        result = await skill.execute({"prompt": "SaaS personas"}, _ctx())
        assert result.success is True
        assert result.data["rag_enabled"] is True
        assert result.data["chunk_count"] == 1

    @patch("app.skills.rag_context_retrieval.httpx.AsyncClient")
    async def test_rag_failure(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        skill = RAGContextRetrieval(
            rag_service_url="http://localhost:8070", rag_enabled=True
        )
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is False
