"""Tests for CAAAnalyzer."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.caa_analyzer import CAAAnalyzer


class TestCAAAnalyzer:
    """Test the CAAAnalyzer 5-phase PAOR engine."""

    def _make_analyzer(
        self,
        mock_anthropic_client,
        mock_event_emitter,
        mock_gcs_client=None,
        mock_redis_manager=None,
        mock_tavily_client=None,
    ):
        """Build a CAAAnalyzer with mocks."""
        return CAAAnalyzer(
            anthropic_client=mock_anthropic_client,
            event_emitter=mock_event_emitter,
            gcs_client=mock_gcs_client,
            redis_manager=mock_redis_manager,
            tavily_client=mock_tavily_client,
        )

    async def test_analyze_two_claude_calls(
        self, mock_anthropic_client, mock_event_emitter
    ):
        """Analyzer makes exactly 2 calls to LLM (architecture + blueprint)."""
        analyzer = self._make_analyzer(mock_anthropic_client, mock_event_emitter)
        await analyzer.analyze(
            prompt="test campaign",
            tenant_id="t1",
            wf1_context={"industry": "SaaS"},
            bpa_context={"statement": "Best SaaS"},
            company_context={"name": "Acme", "industry": "SaaS"},
        )
        assert mock_anthropic_client.generate_json.await_count == 2

    async def test_analyze_includes_tavily_benchmarks(
        self,
        mock_anthropic_client,
        mock_event_emitter,
        mock_tavily_client,
    ):
        """Analyzer passes tavily_benchmarks to result when provided."""
        analyzer = self._make_analyzer(
            mock_anthropic_client,
            mock_event_emitter,
            mock_tavily_client=mock_tavily_client,
        )
        result = await analyzer.analyze(
            prompt="test",
            tenant_id="t1",
            wf1_context={"industry": "SaaS"},
            bpa_context={"statement": "Best"},
            company_context={"name": "Acme"},
            tavily_benchmarks={
                "answer": "CPM $10",
                "results": [],
                "tavily_sources": [{"url": "https://example.com"}],
            },
        )
        assert result["tavily_benchmarks_used"] is True

    async def test_analyze_handles_missing_optional_data(
        self, mock_anthropic_client, mock_event_emitter
    ):
        """Analyzer works without Odoo, RAG, or BAA data."""
        analyzer = self._make_analyzer(mock_anthropic_client, mock_event_emitter)
        result = await analyzer.analyze(
            prompt="test",
            tenant_id="t1",
            wf1_context={"industry": "SaaS"},
            bpa_context={"statement": "Best"},
            company_context={"name": "Acme"},
            odoo_context=None,
            rag_context=None,
            baa_context=None,
        )
        assert result["odoo_data_used"] is False
        assert result["rag_learnings_used"] is False

    async def test_analyze_runs_guardrails(
        self, mock_anthropic_client, mock_event_emitter
    ):
        """Analyzer runs input guardrails and produces a result."""
        analyzer = self._make_analyzer(mock_anthropic_client, mock_event_emitter)
        result = await analyzer.analyze(
            prompt="test",
            tenant_id="t1",
            wf1_context={"industry": "SaaS"},
            bpa_context={"statement": "Best"},
            company_context={"name": "Acme"},
            config={"daily_budget": 500},
        )
        # Result should always contain these keys
        assert "special_ad_category" in result
        assert "meta_api_compatible" in result
        assert "confidence_score" in result
