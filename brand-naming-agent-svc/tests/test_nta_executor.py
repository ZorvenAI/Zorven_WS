"""Tests for NTAExecutor."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.messaging.event_emitter import EventEmitter, EventType
from app.services.nta_executor import NTAExecutor


@pytest.fixture
def event_emitter():
    emitter = AsyncMock(spec=EventEmitter)
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def trace_producer():
    producer = AsyncMock()
    producer.send_trace = AsyncMock()
    return producer


@pytest.fixture
def audit_producer():
    producer = AsyncMock()
    producer.send_audit = AsyncMock()
    return producer


@pytest.fixture
def mock_analyzer():
    analyzer = AsyncMock()
    analyzer.analyze = AsyncMock(
        return_value={
            "query": "test",
            "name_candidates": [
                {"name": "TestBrand", "scores": {"overall": 85}},
            ],
            "shortlisted_names": ["TestBrand"],
            "taglines": [{"tagline": "Test line", "name": "TestBrand"}],
            "naming_brief": {"recommended_name": "TestBrand"},
            "availability_results": {},
            "scoring_summary": {"total": 1},
            "confidence_score": 0.85,
            "findings": [],
            "recommendations": [],
            "sources": [],
            "wf1_context_used": True,
            "bpa_context_used": True,
            "bpv_context_used": True,
            "baa_context_used": False,
            "execution_time_ms": 500,
        }
    )
    return analyzer


@pytest.fixture
def executor(
    mock_analyzer,
    mock_redis_manager,
    trace_producer,
    audit_producer,
    event_emitter,
    mock_context_loader,
):
    return NTAExecutor(
        analyzer=mock_analyzer,
        redis_manager=mock_redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        event_emitter=event_emitter,
        context_loader=mock_context_loader,
    )


class TestExecutorCacheFlow:
    """Test cache hit / miss flow."""

    async def test_cache_hit_returns_cached(
        self, executor, mock_redis_manager, mock_analyzer
    ):
        """When cache has a result, analyzer is NOT called."""
        mock_redis_manager.get_cached_result = AsyncMock(
            return_value={"cached": True, "name_candidates": []}
        )
        result = await executor.execute(
            prompt="test",
            tenant_id="t1",
            previous_outputs={
                "market_research": {},
                "brand_positioning": {},
                "brand_personality": {},
            },
        )
        assert result["cached"] is True
        mock_analyzer.analyze.assert_not_called()

    async def test_cache_miss_calls_analyzer(
        self, executor, mock_redis_manager, mock_analyzer
    ):
        """When cache is empty, analyzer IS called."""
        mock_redis_manager.get_cached_result = AsyncMock(return_value=None)
        result = await executor.execute(
            prompt="test",
            tenant_id="t1",
            previous_outputs={
                "market_research": {"data": True},
                "brand_positioning": {"data": True},
                "brand_personality": {"data": True},
            },
        )
        mock_analyzer.analyze.assert_called_once()
        assert result["confidence_score"] == 0.85


class TestPrerequisiteCheck:
    """Test WF1 + BPA + BPV prerequisite enforcement."""

    async def test_missing_wf1_returns_error(
        self, executor, mock_context_loader
    ):
        """Missing WF1 context prevents analysis."""
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": None,
                "bpa": {"data": True},
                "bpv": {"data": True},
                "company": None,
            }
        )
        result = await executor.execute(
            prompt="test", tenant_id="t1", previous_outputs={}
        )
        assert "Cannot proceed" in result["findings"][0]
        assert "WF1 Brand Discovery" in result["findings"][0]

    async def test_missing_bpa_returns_error(
        self, executor, mock_context_loader
    ):
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"data": True},
                "bpa": None,
                "bpv": {"data": True},
                "company": None,
            }
        )
        result = await executor.execute(
            prompt="test", tenant_id="t1", previous_outputs={}
        )
        assert "BPA Brand Positioning" in result["findings"][0]

    async def test_missing_bpv_returns_error(
        self, executor, mock_context_loader
    ):
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"data": True},
                "bpa": {"data": True},
                "bpv": None,
                "company": None,
            }
        )
        result = await executor.execute(
            prompt="test", tenant_id="t1", previous_outputs={}
        )
        assert "BPV Brand Personality" in result["findings"][0]

    async def test_previous_outputs_satisfy_prereqs(
        self, executor, mock_context_loader, mock_analyzer
    ):
        """previous_outputs can satisfy WF1 + BPA + BPV prereqs."""
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": None,
                "bpa": None,
                "bpv": None,
                "company": None,
            }
        )
        result = await executor.execute(
            prompt="test",
            tenant_id="t1",
            previous_outputs={
                "market_research": {"data": True},
                "brand_positioning": {"data": True},
                "brand_personality": {"data": True},
            },
        )
        # Analyzer should be called because prereqs are met via previous_outputs
        mock_analyzer.analyze.assert_called_once()

    async def test_baa_missing_does_not_block(
        self, executor, mock_context_loader, mock_analyzer
    ):
        """BAA is recommended, not required — analysis proceeds without it."""
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"data": True},
                "bpa": {"data": True},
                "bpv": {"data": True},
                "company": None,
            }
        )
        result = await executor.execute(
            prompt="test", tenant_id="t1", previous_outputs={}
        )
        mock_analyzer.analyze.assert_called_once()


class TestExecutorTracing:
    """Test trace + event emission."""

    async def test_trace_started_and_completed(
        self, executor, trace_producer
    ):
        result = await executor.execute(
            prompt="test",
            tenant_id="t1",
            previous_outputs={
                "market_research": {"data": True},
                "brand_positioning": {"data": True},
                "brand_personality": {"data": True},
            },
        )
        calls = trace_producer.send_trace.call_args_list
        # Started + completed
        assert len(calls) >= 2
        assert calls[0][0][0]["status"] == "started"
        assert calls[-1][0][0]["status"] == "completed"

    async def test_events_emitted_on_context_load(
        self, executor, event_emitter, mock_context_loader
    ):
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": {"data": True},
                "bpa": None,
                "bpv": {"data": True},
                "company": None,
            }
        )
        result = await executor.execute(
            prompt="test",
            tenant_id="t1",
            previous_outputs={
                "brand_positioning": {},
            },
        )
        # Should emit context loaded/missing events
        emit_calls = event_emitter.emit.call_args_list
        event_types = [c[0][0] for c in emit_calls]
        assert EventType.WF1_CONTEXT_LOADED in event_types
        assert EventType.BPA_CONTEXT_MISSING in event_types
        assert EventType.BPV_CONTEXT_LOADED in event_types


class TestExecutorErrorHandling:
    """Test error handling in executor."""

    async def test_analyzer_exception_returns_error_result(
        self, executor, mock_analyzer
    ):
        mock_analyzer.analyze = AsyncMock(
            side_effect=RuntimeError("LLM failure")
        )
        result = await executor.execute(
            prompt="test",
            tenant_id="t1",
            previous_outputs={
                "market_research": {"data": True},
                "brand_positioning": {"data": True},
                "brand_personality": {"data": True},
            },
        )
        assert "Analysis failed" in result["findings"][0]
        assert result["confidence_score"] == 0.0
