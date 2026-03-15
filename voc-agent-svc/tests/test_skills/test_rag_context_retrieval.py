"""Tests for SKL-VoCA-08: RAG Context Retrieval."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.skills.rag_context_retrieval import RAGContextRetrieval


@pytest.fixture
def disabled_rag():
    """RAGContextRetrieval with RAG disabled."""
    return RAGContextRetrieval(
        rag_service_url="http://localhost:8070",
        rag_enabled=False,
    )


@pytest.fixture
def enabled_rag():
    """RAGContextRetrieval with RAG enabled."""
    return RAGContextRetrieval(
        rag_service_url="http://localhost:8070",
        rag_enabled=True,
    )


@pytest.mark.unit
def test_meta_attributes(disabled_rag):
    """Skill meta has correct ID and name."""
    assert disabled_rag.meta.skill_id == "SKL-VoCA-08"
    assert disabled_rag.meta.name == "rag_context_retrieval"
    assert "VIEWER" in disabled_rag.meta.allowed_roles


@pytest.mark.asyncio
@pytest.mark.unit
async def test_disabled_returns_empty(
    disabled_rag, basic_skill_context, basic_input_data
):
    """When RAG is disabled, returns success with empty chunks."""
    result = await disabled_rag.execute(basic_input_data, basic_skill_context)
    assert result.success is True
    assert result.data["chunks"] == []
    assert result.data["rag_enabled"] is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_with_rag_enabled(
    enabled_rag, basic_skill_context, basic_input_data
):
    """When RAG is enabled, calls the RAG service and returns chunks."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "chunks": [
            {
                "content": "Previous VoC report shows positive trend",
                "metadata": {
                    "source_url": "gs://bucket/report.json",
                    "title": "Q4 VoC Report",
                },
                "score": 0.85,
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.skills.rag_context_retrieval.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        result = await enabled_rag.execute(basic_input_data, basic_skill_context)

    assert result.success is True
    assert result.data["rag_enabled"] is True
    assert len(result.data["chunks"]) == 1
    assert result.data["chunks"][0]["score"] == 0.85
