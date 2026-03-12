"""Tests for CIA Executor — full execution pipeline with mocked dependencies."""

from unittest.mock import AsyncMock, MagicMock

from app.api.schemas import (
    CompetitorIntelligenceResponse,
    CompetitorProfile,
    ExecuteRequest,
    SourceItem,
)
from app.cache.redis_manager import RedisManager
from app.logic.competitor_analyzer import CompetitorAnalyzer
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.cia_executor import CIAExecutor


def _make_executor(
    analyzer_result: CompetitorIntelligenceResponse | None = None,
    cached_result: dict | None = None,
    rate_limit_allowed: bool = True,
) -> CIAExecutor:
    """Create a CIAExecutor with fully mocked dependencies."""
    if analyzer_result is None:
        analyzer_result = CompetitorIntelligenceResponse(
            query="test competitors",
            executive_summary="Two competitors identified.",
            competitors=[
                CompetitorProfile(
                    slug="acme-corp",
                    name="Acme Corp",
                    website="https://acme.com",
                    market_position="leader",
                    confidence=0.8,
                )
            ],
            findings=["Acme Corp is the market leader"],
            recommendations=["Focus on differentiation"],
            sources=[
                SourceItem(type="web", title="Acme", url="https://acme.com")
            ],
            confidence_score=0.8,
        )

    analyzer = MagicMock(spec=CompetitorAnalyzer)
    analyzer.analyze = AsyncMock(return_value=analyzer_result)
    analyzer.close = AsyncMock()

    redis_manager = MagicMock(spec=RedisManager)
    redis_manager.check_rate_limit = AsyncMock(return_value=rate_limit_allowed)
    redis_manager.get_cached_result = AsyncMock(return_value=cached_result)
    redis_manager.set_cached_result = AsyncMock()
    redis_manager.close = AsyncMock()

    trace_producer = MagicMock(spec=TraceProducer)
    trace_producer.send_step = AsyncMock()
    trace_producer.stop = AsyncMock()

    audit_producer = MagicMock(spec=AuditProducer)
    audit_producer.send_audit = AsyncMock()
    audit_producer.stop = AsyncMock()

    return CIAExecutor(
        analyzer=analyzer,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
    )


def _make_request(prompt: str = "Identify competitors for Acme AI") -> ExecuteRequest:
    return ExecuteRequest(
        input_prompt=prompt,
        input_context={"job_id": "test-job-123"},
        config={"focus": "competitor_profiling"},
    )


class TestExecuteHappyPath:
    async def test_returns_competitor_intelligence_response(self):
        executor = _make_executor()
        result = await executor.execute(_make_request(), "tenant-1")
        assert isinstance(result, CompetitorIntelligenceResponse)

    async def test_calls_analyzer(self):
        executor = _make_executor()
        await executor.execute(_make_request(), "tenant-1")
        executor.analyzer.analyze.assert_awaited_once()

    async def test_caches_result(self):
        executor = _make_executor()
        await executor.execute(_make_request(), "tenant-1")
        executor.redis_manager.set_cached_result.assert_awaited_once()

    async def test_emits_trace_events(self):
        executor = _make_executor()
        await executor.execute(_make_request(), "tenant-1")
        assert executor.trace_producer.send_step.await_count >= 2

    async def test_emits_audit_event(self):
        executor = _make_executor()
        await executor.execute(_make_request(), "tenant-1")
        executor.audit_producer.send_audit.assert_awaited_once()

    async def test_passes_user_role_from_tenant_context(self):
        executor = _make_executor()
        request = ExecuteRequest(
            input_prompt="test competitors",
            input_context={"job_id": "j1"},
            tenant_context={"tenant_id": "t1", "user_role": "VIEWER"},
        )
        await executor.execute(request, "t1")
        call_kwargs = executor.analyzer.analyze.call_args.kwargs
        assert call_kwargs["user_role"] == "VIEWER"


class TestCacheBehavior:
    async def test_returns_cached_result(self):
        cached = {
            "query": "cached competitor query",
            "executive_summary": "Cached summary",
            "competitors": [],
            "competitor_matrix": {},
            "positioning_gaps": [],
            "positioning_map": {},
            "benchmarking_report": {},
            "findings": ["cached finding"],
            "recommendations": [],
            "sources": [],
            "raw_context": "",
            "confidence_score": 0.9,
            "methodology_notes": [],
        }
        executor = _make_executor(cached_result=cached)
        result = await executor.execute(_make_request(), "tenant-1")
        assert result.query == "cached competitor query"
        assert result.confidence_score == 0.9
        executor.analyzer.analyze.assert_not_awaited()

    async def test_cache_miss_calls_analyzer(self):
        executor = _make_executor(cached_result=None)
        await executor.execute(_make_request(), "tenant-1")
        executor.analyzer.analyze.assert_awaited_once()


class TestClose:
    async def test_close_cleans_up_all(self):
        executor = _make_executor()
        await executor.close()
        executor.redis_manager.close.assert_awaited_once()
        executor.trace_producer.stop.assert_awaited_once()
        executor.audit_producer.stop.assert_awaited_once()
        executor.analyzer.close.assert_awaited_once()


class TestCacheKeyBuilding:
    def test_same_inputs_same_key(self):
        key1 = CIAExecutor._build_cache_key("test", {"focus": "swot"})
        key2 = CIAExecutor._build_cache_key("test", {"focus": "swot"})
        assert key1 == key2

    def test_different_prompts_different_keys(self):
        key1 = CIAExecutor._build_cache_key("test1", {})
        key2 = CIAExecutor._build_cache_key("test2", {})
        assert key1 != key2

    def test_different_configs_different_keys(self):
        key1 = CIAExecutor._build_cache_key("test", {"focus": "swot"})
        key2 = CIAExecutor._build_cache_key("test", {"focus": "benchmarking"})
        assert key1 != key2


class TestNoRedis:
    async def test_executes_without_redis(self):
        analyzer = MagicMock(spec=CompetitorAnalyzer)
        analyzer.analyze = AsyncMock(
            return_value=CompetitorIntelligenceResponse(
                query="test",
                findings=["f1"],
                confidence_score=0.5,
            )
        )
        analyzer.close = AsyncMock()

        executor = CIAExecutor(
            analyzer=analyzer,
            redis_manager=None,
            trace_producer=None,
            audit_producer=None,
        )
        result = await executor.execute(_make_request(), "tenant-1")
        assert isinstance(result, CompetitorIntelligenceResponse)
