"""Tests for BPAExecutor."""

import pytest
from unittest.mock import AsyncMock, patch

from app.messaging.event_emitter import EventEmitter
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.bpa_analyzer import BPAAnalyzer
from app.services.bpa_executor import BPAExecutor
from app.services.wf1_loader import WF1ContextLoader


@pytest.fixture
def mock_analyzer():
    analyzer = AsyncMock(spec=BPAAnalyzer)
    analyzer.analyze = AsyncMock(
        return_value={
            "query": "test",
            "recommended_positioning": {"statement": "Test position"},
            "alternative_positions": [],
            "positioning_candidates": [{"statement": "Test position"}],
            "canvas": {},
            "perceptual_maps": [],
            "differentiation": {},
            "strategy": {},
            "confidence_score": 0.85,
            "wf1_context_used": True,
            "execution_time_ms": 1000,
            "findings": ["Test finding"],
            "recommendations": ["Test recommendation"],
            "sources": [],
        }
    )
    return analyzer


@pytest.fixture
def mock_trace():
    trace = AsyncMock(spec=TraceProducer)
    trace.send_trace = AsyncMock()
    return trace


@pytest.fixture
def mock_audit():
    audit = AsyncMock(spec=AuditProducer)
    audit.send_event = AsyncMock()
    return audit


@pytest.fixture
def mock_event_emitter():
    return AsyncMock(spec=EventEmitter)


@pytest.fixture
def executor(
    mock_analyzer,
    mock_redis_manager,
    mock_trace,
    mock_audit,
    mock_event_emitter,
    mock_wf1_loader,
):
    return BPAExecutor(
        analyzer=mock_analyzer,
        redis_manager=mock_redis_manager,
        trace_producer=mock_trace,
        audit_producer=mock_audit,
        event_emitter=mock_event_emitter,
        wf1_loader=mock_wf1_loader,
    )


class TestBPAExecutor:
    """Test BPAExecutor behavior."""

    async def test_execute_calls_analyzer(self, executor, mock_analyzer):
        result = await executor.execute(
            prompt="Test positioning",
            input_context={"job_id": "test-123"},
            tenant_context={"user_role": "EDITOR"},
            config={},
            previous_outputs={},
            tenant_id="test-tenant",
        )
        assert mock_analyzer.analyze.called
        assert result["query"] == "test"

    async def test_execute_returns_cached_result(
        self, executor, mock_redis_manager, mock_analyzer
    ):
        cached_data = {"query": "cached", "confidence_score": 0.9}
        mock_redis_manager.get_cached_result = AsyncMock(return_value=cached_data)
        result = await executor.execute(
            prompt="Test",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert result == cached_data
        assert not mock_analyzer.analyze.called

    async def test_execute_loads_wf1_context(self, executor, mock_wf1_loader):
        mock_wf1_loader.load = AsyncMock(
            return_value={
                "mra": {"market_overview": "Test"},
                "snapshot_id": "snap-123",
            }
        )
        await executor.execute(
            prompt="Test",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
            tenant_id="test-tenant",
        )
        mock_wf1_loader.load.assert_called_once_with("test-tenant")

    async def test_execute_handles_wf1_failure(
        self, executor, mock_wf1_loader, mock_analyzer
    ):
        mock_wf1_loader.load = AsyncMock(return_value=None)
        result = await executor.execute(
            prompt="Test",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        # Should still succeed (with empty WF1 context)
        assert mock_analyzer.analyze.called

    async def test_execute_handles_analyzer_error(self, executor, mock_analyzer):
        mock_analyzer.analyze = AsyncMock(side_effect=Exception("Analysis failed"))
        result = await executor.execute(
            prompt="Test",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert "Analysis failed" in result["findings"][0]
        assert result["confidence_score"] == 0.0

    async def test_execute_emits_trace_events(self, executor, mock_trace):
        await executor.execute(
            prompt="Test",
            input_context={"job_id": "j-1"},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        # Should emit started and completed traces
        assert mock_trace.send_trace.call_count >= 2

    async def test_execute_caches_result(self, executor, mock_redis_manager):
        await executor.execute(
            prompt="Test",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert mock_redis_manager.cache_result.called
