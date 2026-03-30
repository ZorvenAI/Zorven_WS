"""Tests for BSAExecutor."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.bsa_executor import BSAExecutor


@pytest.fixture
def executor(mock_redis_manager, mock_context_loader, mock_gcs_client):
    """Create an executor with mocked dependencies."""
    mock_analyzer = AsyncMock()
    mock_analyzer.analyze = AsyncMock(
        return_value={
            "origin_story": {
                "archetype_used": "Hero",
                "versions": [
                    {
                        "version_label": "short",
                        "word_count": 500,
                        "content": "A short origin story.",
                        "archetype_arc_alignment": 0.85,
                        "emotional_resonance_score": 0.80,
                        "voice_consistency_score": 0.78,
                    }
                ],
            },
            "mission_vision": {"mission": {"recommended": "Our mission"}},
            "pitches": {"pitch_30s": {"content": "30s pitch"}},
            "channel_narratives": {"channel_consistency_score": 0.82},
            "narrative_package": {
                "overall_confidence": 0.81,
                "positioning_narrative_alignment": 0.79,
            },
            "confidence_score": 0.81,
            "execution_time_ms": 4200,
        }
    )

    mock_event_emitter = AsyncMock()
    mock_kafka_trace = AsyncMock()
    mock_kafka_trace.send_trace = AsyncMock()
    mock_kafka_audit = AsyncMock()
    mock_kafka_audit.send_audit = AsyncMock()

    ex = BSAExecutor(
        analyzer=mock_analyzer,
        redis_manager=mock_redis_manager,
        trace_producer=mock_kafka_trace,
        audit_producer=mock_kafka_audit,
        event_emitter=mock_event_emitter,
        context_loader=mock_context_loader,
        gcs_client=mock_gcs_client,
    )
    return ex


class TestBSAExecutor:
    """Test BSAExecutor core flows."""

    async def test_execute_returns_result(self, executor):
        result = await executor.execute(
            prompt="Create brand story",
            tenant_id="test-tenant",
            input_context={"company_name": "TestCo"},
            tenant_context={"tenant_id": "test-tenant"},
            config={},
            previous_outputs={},
        )
        assert result is not None
        assert "origin_story" in result
        assert "confidence_score" in result

    async def test_execute_returns_cached_result(self, executor, mock_redis_manager):
        cached = {"origin_story": {"cached": True}, "confidence_score": 0.75}
        mock_redis_manager.get_cached_result = AsyncMock(return_value=cached)

        result = await executor.execute(
            prompt="Create brand story",
            tenant_id="test-tenant",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert result.get("origin_story", {}).get("cached") is True

    async def test_execute_loads_context(self, executor, mock_context_loader):
        await executor.execute(
            prompt="Create brand story",
            tenant_id="test-tenant",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        mock_context_loader.load_all.assert_awaited_once()

    async def test_execute_caches_result(self, executor, mock_redis_manager):
        await executor.execute(
            prompt="Create brand story",
            tenant_id="test-tenant",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        mock_redis_manager.cache_result.assert_awaited_once()

    async def test_execute_handles_analyzer_error(self, executor):
        executor._analyzer.analyze = AsyncMock(
            side_effect=Exception("LLM call failed")
        )
        result = await executor.execute(
            prompt="Create brand story",
            tenant_id="test-tenant",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert result.get("error") is not None or result.get("confidence_score") == 0.0
