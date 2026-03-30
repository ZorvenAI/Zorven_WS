"""Tests for CAAExecutor."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.caa_executor import CAAExecutor


class TestCAAExecutor:
    """Test the CAAExecutor orchestration logic."""

    def _make_executor(
        self,
        mock_redis_manager,
        mock_kafka_trace,
        mock_kafka_audit,
        mock_event_emitter,
        mock_context_loader,
        mock_gcs_client,
        mock_anthropic_client,
    ):
        """Build a CAAExecutor with all mocks."""
        analyzer = AsyncMock()
        analyzer.analyze = AsyncMock(
            return_value={
                "query": "test",
                "blueprint": {"campaign_name": "Test"},
                "funnel_map": {},
                "targeting_specs": [],
                "placement_budget": {},
                "test_plan": {},
                "kpi_targets": {},
                "performance_projections": {},
                "risk_assessment": {},
                "creative_briefs": [],
                "special_ad_category": "NONE",
                "meta_api_compatible": True,
                "confidence_score": 0.85,
                "findings": [],
                "recommendations": [],
                "sources": [],
                "wf1_context_used": True,
                "wf2_context_used": False,
                "bpa_context_used": True,
                "company_context_used": True,
                "tavily_benchmarks_used": False,
                "odoo_data_used": False,
                "rag_learnings_used": False,
                "gcs_uri": "",
                "execution_time_ms": 100,
            }
        )
        analyzer._tavily = None
        return CAAExecutor(
            analyzer=analyzer,
            redis_manager=mock_redis_manager,
            trace_producer=mock_kafka_trace,
            audit_producer=mock_kafka_audit,
            event_emitter=mock_event_emitter,
            context_loader=mock_context_loader,
            gcs_client=mock_gcs_client,
        )

    async def test_execute_with_cache_hit(
        self,
        mock_redis_manager,
        mock_kafka_trace,
        mock_kafka_audit,
        mock_event_emitter,
        mock_context_loader,
        mock_gcs_client,
        mock_anthropic_client,
    ):
        """Cache hit returns cached result without calling analyzer."""
        cached_result = {"query": "cached", "confidence_score": 0.9}
        mock_redis_manager.get_cached_result = AsyncMock(return_value=cached_result)

        executor = self._make_executor(
            mock_redis_manager,
            mock_kafka_trace,
            mock_kafka_audit,
            mock_event_emitter,
            mock_context_loader,
            mock_gcs_client,
            mock_anthropic_client,
        )
        result = await executor.execute(
            prompt="test", tenant_id="t1", input_context={"job_id": "j1"}
        )
        assert result == cached_result
        mock_context_loader.load_all.assert_not_called()

    async def test_execute_loads_context_parallel(
        self,
        mock_redis_manager,
        mock_kafka_trace,
        mock_kafka_audit,
        mock_event_emitter,
        mock_context_loader,
        mock_gcs_client,
        mock_anthropic_client,
    ):
        """Executor calls context_loader.load_all once."""
        executor = self._make_executor(
            mock_redis_manager,
            mock_kafka_trace,
            mock_kafka_audit,
            mock_event_emitter,
            mock_context_loader,
            mock_gcs_client,
            mock_anthropic_client,
        )
        await executor.execute(prompt="test", tenant_id="t1")
        mock_context_loader.load_all.assert_awaited_once_with("t1")

    async def test_execute_missing_prerequisites_returns_error(
        self,
        mock_redis_manager,
        mock_kafka_trace,
        mock_kafka_audit,
        mock_event_emitter,
        mock_context_loader,
        mock_gcs_client,
        mock_anthropic_client,
    ):
        """Missing WF1 context returns error findings."""
        mock_context_loader.load_all = AsyncMock(
            return_value={
                "wf1": None,
                "bpa": None,
                "wf2_chain": None,
                "company": None,
                "baa": None,
                "odoo": None,
                "rag": None,
            }
        )
        executor = self._make_executor(
            mock_redis_manager,
            mock_kafka_trace,
            mock_kafka_audit,
            mock_event_emitter,
            mock_context_loader,
            mock_gcs_client,
            mock_anthropic_client,
        )
        result = await executor.execute(prompt="test", tenant_id="t1")
        assert result["confidence_score"] == 0.0
        assert any("Cannot proceed" in f for f in result["findings"])

    async def test_execute_budget_guardrail_warning(
        self,
        mock_redis_manager,
        mock_kafka_trace,
        mock_kafka_audit,
        mock_event_emitter,
        mock_context_loader,
        mock_gcs_client,
        mock_anthropic_client,
    ):
        """Executor completes even with budget in config."""
        executor = self._make_executor(
            mock_redis_manager,
            mock_kafka_trace,
            mock_kafka_audit,
            mock_event_emitter,
            mock_context_loader,
            mock_gcs_client,
            mock_anthropic_client,
        )
        result = await executor.execute(
            prompt="test", tenant_id="t1", config={"daily_budget": 500}
        )
        assert "query" in result

    async def test_execute_calls_analyzer(
        self,
        mock_redis_manager,
        mock_kafka_trace,
        mock_kafka_audit,
        mock_event_emitter,
        mock_context_loader,
        mock_gcs_client,
        mock_anthropic_client,
    ):
        """Executor delegates to analyzer.analyze."""
        executor = self._make_executor(
            mock_redis_manager,
            mock_kafka_trace,
            mock_kafka_audit,
            mock_event_emitter,
            mock_context_loader,
            mock_gcs_client,
            mock_anthropic_client,
        )
        await executor.execute(prompt="test", tenant_id="t1")
        executor._analyzer.analyze.assert_awaited_once()

    async def test_execute_persists_to_gcs(
        self,
        mock_redis_manager,
        mock_kafka_trace,
        mock_kafka_audit,
        mock_event_emitter,
        mock_context_loader,
        mock_gcs_client,
        mock_anthropic_client,
    ):
        """Executor calls gcs_client.upload_blueprint after analysis."""
        executor = self._make_executor(
            mock_redis_manager,
            mock_kafka_trace,
            mock_kafka_audit,
            mock_event_emitter,
            mock_context_loader,
            mock_gcs_client,
            mock_anthropic_client,
        )
        result = await executor.execute(prompt="test", tenant_id="t1")
        mock_gcs_client.upload_blueprint.assert_awaited_once()
        assert result["gcs_uri"] != ""
