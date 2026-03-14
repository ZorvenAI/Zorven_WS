"""Tests for TCIA Executor — cache, delegation, tracing, and auditing."""

from unittest.mock import AsyncMock, MagicMock

from app.services.tcia_executor import TCIAExecutor


def _make_executor(
    analyzer_result: dict | None = None,
    cached_result: dict | None = None,
) -> TCIAExecutor:
    """Create a TCIAExecutor with fully mocked dependencies."""
    if analyzer_result is None:
        analyzer_result = {
            "trend_report": {
                "executive_summary": "Test trends identified.",
                "trend_scorecard": [],
                "confidence_score": 0.8,
            },
            "scored_trends": [
                {
                    "trend_slug": "ev-charging-growth",
                    "topic": "EV Charging Growth",
                    "relevance_score": 82,
                    "recommendation": "capitalize",
                }
            ],
            "opportunity_alerts": [
                {
                    "alert_id": "alert-001",
                    "trend_slug": "ev-charging-growth",
                    "relevance_score": 82,
                }
            ],
            "sources": [
                {"type": "web", "title": "EV Report", "url": "https://example.com/ev"}
            ],
            "findings": ["EV charging market growing rapidly"],
            "confidence_score": 0.8,
        }

    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value=analyzer_result)

    redis_manager = AsyncMock()
    redis_manager.get_cached_result = AsyncMock(return_value=cached_result)
    redis_manager.cache_result = AsyncMock()

    trace_producer = AsyncMock()
    trace_producer.send_step = AsyncMock()

    audit_producer = AsyncMock()
    audit_producer.send_event = AsyncMock()

    return TCIAExecutor(
        analyzer=analyzer,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
    )


class TestCacheHit:
    """Cache hit returns cached result without calling analyzer."""

    async def test_cache_hit_returns_cached(self) -> None:
        cached = {
            "trend_report": {"executive_summary": "Cached trends"},
            "scored_trends": [],
            "sources": [],
            "confidence_score": 0.9,
        }
        executor = _make_executor(cached_result=cached)
        result = await executor.execute(
            prompt="test trends",
            input_context={"job_id": "j1"},
            tenant_context={"user_role": "EDITOR"},
            config={},
            previous_outputs={},
            tenant_id="t1",
        )
        assert result == cached
        executor._analyzer.analyze.assert_not_awaited()

    async def test_cache_hit_emits_completed_trace(self) -> None:
        cached = {"trend_report": {}, "scored_trends": []}
        executor = _make_executor(cached_result=cached)
        await executor.execute(
            prompt="test",
            input_context={"job_id": "j1"},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        # Should have at least 2 trace calls: started + cache hit
        assert executor._trace.send_step.await_count >= 2


class TestCacheMiss:
    """Cache miss delegates to analyzer and caches the result."""

    async def test_cache_miss_calls_analyzer(self) -> None:
        executor = _make_executor(cached_result=None)
        await executor.execute(
            prompt="analyze trends",
            input_context={"job_id": "j2"},
            tenant_context={"user_role": "EDITOR"},
            config={},
            previous_outputs={},
            tenant_id="t1",
        )
        executor._analyzer.analyze.assert_awaited_once()

    async def test_cache_miss_stores_result(self) -> None:
        executor = _make_executor(cached_result=None)
        await executor.execute(
            prompt="analyze trends",
            input_context={"job_id": "j2"},
            tenant_context={},
            config={},
            previous_outputs={},
            tenant_id="t1",
        )
        executor._redis.cache_result.assert_awaited_once()

    async def test_cache_miss_emits_audit_event(self) -> None:
        executor = _make_executor(cached_result=None)
        await executor.execute(
            prompt="analyze trends",
            input_context={"job_id": "j2"},
            tenant_context={},
            config={},
            previous_outputs={},
            tenant_id="t1",
        )
        executor._audit.send_event.assert_awaited_once()
        event = executor._audit.send_event.call_args[0][0]
        assert event["event_type"] == "analysis.completed"
        assert event["tenant_id"] == "t1"

    async def test_returns_correct_result(self) -> None:
        expected = {
            "trend_report": {"executive_summary": "Fresh analysis"},
            "scored_trends": [
                {"trend_slug": "test-trend", "relevance_score": 75}
            ],
            "opportunity_alerts": [],
            "sources": [],
            "findings": ["New finding"],
            "confidence_score": 0.75,
        }
        executor = _make_executor(analyzer_result=expected, cached_result=None)
        result = await executor.execute(
            prompt="test",
            input_context={"job_id": "j3"},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert result["trend_report"]["executive_summary"] == "Fresh analysis"
        assert result["confidence_score"] == 0.75


class TestTraceEvents:
    """Verify trace producer calls during execution."""

    async def test_trace_events_emitted_on_success(self) -> None:
        executor = _make_executor(cached_result=None)
        await executor.execute(
            prompt="test",
            input_context={"job_id": "j4"},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        # At least: 1 start + 1 completed
        assert executor._trace.send_step.await_count >= 2

    async def test_trace_events_on_cache_hit(self) -> None:
        cached = {"scored_trends": []}
        executor = _make_executor(cached_result=cached)
        await executor.execute(
            prompt="test",
            input_context={"job_id": "j5"},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        # Started + Cache hit
        assert executor._trace.send_step.await_count >= 2

    async def test_trace_failure_on_exception(self) -> None:
        executor = _make_executor(cached_result=None)
        executor._analyzer.analyze = AsyncMock(
            side_effect=RuntimeError("LLM timeout")
        )
        result = await executor.execute(
            prompt="test",
            input_context={"job_id": "j6"},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        # Should have error key in result
        assert "error" in result
        # Trace should include FAILED status
        assert executor._trace.send_step.await_count >= 2


class TestErrorHandling:
    """Executor handles analyzer failures gracefully."""

    async def test_analyzer_exception_returns_error_result(self) -> None:
        executor = _make_executor(cached_result=None)
        executor._analyzer.analyze = AsyncMock(
            side_effect=ValueError("Analysis failed")
        )
        result = await executor.execute(
            prompt="test",
            input_context={"job_id": "j7"},
            tenant_context={},
            config={},
            previous_outputs={},
        )
        assert "error" in result
        assert "Analysis failed" in result["error"]
        assert result["scored_trends"] == []
        assert result["sources"] == []
