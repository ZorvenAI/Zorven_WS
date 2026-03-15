"""Tests for VoCAExecutor."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.voc_executor import VoCAExecutor
from app.events.catalog import EventEmitter


@pytest.fixture
def mock_executor_deps():
    """Create all mocked dependencies for VoCAExecutor."""
    analyzer = AsyncMock()
    redis_manager = AsyncMock()
    trace_producer = AsyncMock()
    audit_producer = AsyncMock()
    event_emitter = AsyncMock(spec=EventEmitter)

    trace_producer.send_trace = AsyncMock()
    audit_producer.send_event = AsyncMock()
    event_emitter.emit = AsyncMock()

    return {
        "analyzer": analyzer,
        "redis_manager": redis_manager,
        "trace_producer": trace_producer,
        "audit_producer": audit_producer,
        "event_emitter": event_emitter,
    }


@pytest.fixture
def executor(mock_executor_deps):
    """VoCAExecutor with fully mocked dependencies."""
    return VoCAExecutor(**mock_executor_deps)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_executor_cache_hit(executor, mock_executor_deps):
    """When Redis returns a cached result, the analyzer is NOT called."""
    cached_result = {
        "query": "cached query",
        "operating_mode": "external_only",
        "voc_health_score": 55.0,
        "confidence_score": 0.8,
    }
    mock_executor_deps["redis_manager"].get_cached_result = AsyncMock(
        return_value=cached_result
    )

    result = await executor.execute(
        prompt="cached query",
        input_context={"company_name": "TestCorp"},
        tenant_context={"tenant_id": "t1", "user_role": "EDITOR"},
        config={},
        previous_outputs={},
        tenant_id="t1",
    )

    assert result == cached_result
    # Analyzer should NOT have been called
    mock_executor_deps["analyzer"].analyze.assert_not_called()
    # Trace should show completed from cache
    mock_executor_deps["trace_producer"].send_trace.assert_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_executor_cache_miss(executor, mock_executor_deps):
    """When cache misses, the analyzer.analyze() is called and result is cached."""
    mock_executor_deps["redis_manager"].get_cached_result = AsyncMock(
        return_value=None
    )
    analysis_result = {
        "query": "analyze feedback",
        "operating_mode": "external_only",
        "voc_health_score": 60.0,
        "themes": {"themes": [{"theme_slug": "support"}]},
        "sources": [{"url": "http://example.com"}],
        "findings": ["Finding 1"],
        "confidence_score": 0.75,
        "data_coverage_score": 50.0,
    }
    mock_executor_deps["analyzer"].analyze = AsyncMock(
        return_value=analysis_result
    )

    result = await executor.execute(
        prompt="analyze feedback",
        input_context={"company_name": "TestCorp"},
        tenant_context={"tenant_id": "t1", "user_role": "EDITOR"},
        config={},
        previous_outputs={},
        tenant_id="t1",
    )

    assert result == analysis_result
    # Analyzer should have been called
    mock_executor_deps["analyzer"].analyze.assert_called_once()
    # Result should have been cached
    mock_executor_deps["redis_manager"].cache_result.assert_called_once()
    # Audit event should have been sent
    mock_executor_deps["audit_producer"].send_event.assert_called()
