"""Tests for MRA Executor — full execution pipeline with mocked dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.schemas import ExecuteRequest, MarketResearchResponse, SourceItem
from app.cache.redis_manager import RedisManager
from app.logic.guardrails import InputGuardrail, OutputGuardrail
from app.logic.market_researcher import MarketResearcher
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.mra_executor import MRAExecutor


def _make_executor(
    researcher_result: MarketResearchResponse | None = None,
    cached_result: dict | None = None,
    rate_limit_allowed: bool = True,
) -> MRAExecutor:
    """Create an MRAExecutor with fully mocked dependencies."""
    if researcher_result is None:
        researcher_result = MarketResearchResponse(
            query="test",
            market_overview="Test overview",
            findings=["Finding 1"],
            recommendations=["Recommendation 1"],
            sources=[SourceItem(type="web", title="Test", url="https://example.com")],
            confidence_score=0.8,
        )

    researcher = MagicMock(spec=MarketResearcher)
    researcher.research = AsyncMock(return_value=researcher_result)
    researcher.close = AsyncMock()

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

    return MRAExecutor(
        researcher=researcher,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        input_guard=InputGuardrail(),
        output_guard=OutputGuardrail(),
    )


def _make_request(prompt: str = "What is the AI market size?") -> ExecuteRequest:
    return ExecuteRequest(
        input_prompt=prompt,
        input_context={"job_id": "test-job-123"},
        config={"focus": "sizing"},
    )


class TestExecuteHappyPath:
    async def test_returns_market_research_response(self):
        executor = _make_executor()
        result = await executor.execute(_make_request(), "tenant-1")
        assert isinstance(result, MarketResearchResponse)

    async def test_calls_researcher(self):
        executor = _make_executor()
        await executor.execute(_make_request(), "tenant-1")
        executor.researcher.research.assert_awaited_once()

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
            input_prompt="test market",
            input_context={"job_id": "j1"},
            tenant_context={"tenant_id": "t1", "user_role": "VIEWER"},
        )
        await executor.execute(request, "t1")
        call_kwargs = executor.researcher.research.call_args.kwargs
        assert call_kwargs["user_role"] == "VIEWER"


class TestCacheBehavior:
    async def test_returns_cached_result(self):
        cached = {
            "query": "cached query",
            "market_overview": "cached overview",
            "findings": ["cached finding"],
            "recommendations": [],
            "sources": [],
            "market_sizing": {},
            "competitive_landscape": [],
            "industry_trends": [],
            "economic_indicators": {},
            "raw_context": "",
            "confidence_score": 0.9,
            "methodology_notes": [],
        }
        executor = _make_executor(cached_result=cached)
        result = await executor.execute(_make_request(), "tenant-1")
        assert result.query == "cached query"
        assert result.confidence_score == 0.9
        executor.researcher.research.assert_not_awaited()

    async def test_cache_miss_calls_researcher(self):
        executor = _make_executor(cached_result=None)
        await executor.execute(_make_request(), "tenant-1")
        executor.researcher.research.assert_awaited_once()


class TestInputGuardrail:
    async def test_empty_prompt_rejected(self):
        executor = _make_executor()
        with pytest.raises(HTTPException) as exc_info:
            await executor.execute(_make_request(prompt=""), "tenant-1")
        assert exc_info.value.status_code == 400

    async def test_prompt_with_ssn_rejected(self):
        executor = _make_executor()
        with pytest.raises(HTTPException) as exc_info:
            await executor.execute(
                _make_request(prompt="Research 123-45-6789 market"), "tenant-1"
            )
        assert exc_info.value.status_code == 400


class TestOutputGuardrail:
    async def test_confidence_clamped(self):
        response = MarketResearchResponse(
            query="test", confidence_score=1.5, findings=["f1"]
        )
        executor = _make_executor(researcher_result=response)
        result = await executor.execute(_make_request(), "tenant-1")
        assert result.confidence_score == 1.0


class TestClose:
    async def test_close_cleans_up_all(self):
        executor = _make_executor()
        await executor.close()
        executor.redis_manager.close.assert_awaited_once()
        executor.trace_producer.stop.assert_awaited_once()
        executor.audit_producer.stop.assert_awaited_once()
        executor.researcher.close.assert_awaited_once()


class TestCacheKeyBuilding:
    def test_same_inputs_same_key(self):
        key1 = MRAExecutor._build_cache_key("test", {"focus": "sizing"})
        key2 = MRAExecutor._build_cache_key("test", {"focus": "sizing"})
        assert key1 == key2

    def test_different_prompts_different_keys(self):
        key1 = MRAExecutor._build_cache_key("test1", {})
        key2 = MRAExecutor._build_cache_key("test2", {})
        assert key1 != key2

    def test_different_configs_different_keys(self):
        key1 = MRAExecutor._build_cache_key("test", {"focus": "sizing"})
        key2 = MRAExecutor._build_cache_key("test", {"focus": "trends"})
        assert key1 != key2


class TestNoRedis:
    async def test_executes_without_redis(self):
        researcher = MagicMock(spec=MarketResearcher)
        researcher.research = AsyncMock(
            return_value=MarketResearchResponse(
                query="test", findings=["f1"], confidence_score=0.5
            )
        )
        researcher.close = AsyncMock()

        executor = MRAExecutor(
            researcher=researcher,
            redis_manager=None,
            trace_producer=None,
            audit_producer=None,
        )
        result = await executor.execute(_make_request(), "tenant-1")
        assert isinstance(result, MarketResearchResponse)
