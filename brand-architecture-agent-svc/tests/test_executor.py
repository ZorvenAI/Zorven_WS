"""Tests for BAAExecutor."""

import pytest
from unittest.mock import AsyncMock

from app.messaging.event_emitter import EventEmitter
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.baa_analyzer import BAAAnalyzer
from app.services.baa_executor import BAAExecutor
from app.services.context_loader import BAAContextLoader


@pytest.fixture
def mock_analyzer():
    analyzer = AsyncMock(spec=BAAAnalyzer)
    analyzer.analyze = AsyncMock(
        return_value={
            "query": "test",
            "recommendation": {
                "recommended_model": "hybrid",
                "model_scores": [],
                "confidence_score": 0.85,
            },
            "hierarchy": {
                "root": {"name": "TestBrand"},
                "total_depth": 2,
                "total_nodes": 3,
            },
            "naming_hierarchy": {"naming_pattern": "prefix", "consistency_score": 80},
            "growth_path": {"phases": [{"phase": 1}]},
            "strategy": {},
            "confidence_score": 0.85,
            "wf1_context_used": True,
            "bpa_context_used": True,
            "execution_time_ms": 1500,
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
    mock_context_loader,
):
    return BAAExecutor(
        analyzer=mock_analyzer,
        redis_manager=mock_redis_manager,
        trace_producer=mock_trace,
        audit_producer=mock_audit,
        event_emitter=mock_event_emitter,
        context_loader=mock_context_loader,
    )


class TestBAAExecutor:
    """Test BAAExecutor behavior."""

    async def test_execute_returns_prerequisite_error_without_context(
        self, executor, mock_context_loader, mock_analyzer
    ):
        """BAA requires both WF1 and BPA — should fail without them."""
        mock_context_loader.load_all = AsyncMock(
            return_value={"wf1": None, "bpa": None, "company": None}
        )
        result = await executor.execute(
            prompt="Test architecture",
            input_context={"job_id": "test-123"},
            tenant_context={"user_role": "EDITOR"},
            config={},
            previous_outputs={},
            tenant_id="test-tenant",
        )
        assert "Cannot proceed" in result["findings"][0]
        assert not mock_analyzer.analyze.called

    async def test_execute_calls_analyzer_with_contexts(
        self, executor, mock_analyzer, mock_context_loader
    ):
        """When contexts are available, analyzer should be called."""
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"mra": {}, "cia": {}},
                "bpa": {"recommended_positioning": {"statement": "test"}},
                "company": {"name": "TestCorp"},
            }
        )
        result = await executor.execute(
            prompt="Test architecture",
            input_context={"job_id": "test-123"},
            tenant_context={"user_role": "EDITOR"},
            config={},
            previous_outputs={},
            tenant_id="test-tenant",
        )
        assert mock_analyzer.analyze.called
        assert result["query"] == "test"

    async def test_execute_works_with_previous_outputs_only(
        self, executor, mock_analyzer, mock_context_loader
    ):
        """Should work when contexts come from previous_outputs."""
        mock_context_loader.load_all = AsyncMock(
            return_value={"wf1": None, "bpa": None, "company": None}
        )
        result = await executor.execute(
            prompt="Test architecture",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={
                "market_research": {"tam": "$10B"},
                "brand_positioning": {"recommended_positioning": {"statement": "test"}},
            },
            tenant_id="test-tenant",
        )
        assert mock_analyzer.analyze.called

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

    async def test_execute_handles_analyzer_error(
        self, executor, mock_analyzer, mock_context_loader
    ):
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"mra": {}},
                "bpa": {"recommended_positioning": {}},
                "company": None,
            }
        )
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

    async def test_execute_emits_trace_events(
        self, executor, mock_trace, mock_context_loader
    ):
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"mra": {}},
                "bpa": {"recommended_positioning": {}},
                "company": None,
            }
        )
        await executor.execute(
            prompt="Test",
            input_context={"job_id": "j-1"},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        # Should emit started and completed traces
        assert mock_trace.send_trace.call_count >= 2

    async def test_execute_caches_result(
        self, executor, mock_redis_manager, mock_context_loader
    ):
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"mra": {}},
                "bpa": {"recommended_positioning": {}},
                "company": None,
            }
        )
        await executor.execute(
            prompt="Test",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert mock_redis_manager.cache_result.called

    async def test_execute_updates_architecture_registry(
        self, executor, mock_redis_manager, mock_context_loader
    ):
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"mra": {}},
                "bpa": {"recommended_positioning": {}},
                "company": None,
            }
        )
        await executor.execute(
            prompt="Test",
            input_context={},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert mock_redis_manager.save_architecture.called
