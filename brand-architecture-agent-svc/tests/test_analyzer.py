"""Tests for BAAAnalyzer."""

import pytest
from unittest.mock import AsyncMock

from app.messaging.event_emitter import EventEmitter
from app.services.anthropic_client import AnthropicClient
from app.services.baa_analyzer import BAAAnalyzer


@pytest.fixture
def mock_llm():
    llm = AsyncMock(spec=AnthropicClient)
    llm.generate_json = AsyncMock(
        return_value={
            "recommendation": {
                "recommended_model": "hybrid",
                "model_scores": [
                    {
                        "model": "hybrid",
                        "positioning_alignment": 22,
                        "audience_fit": 20,
                        "competitive_diff": 18,
                        "operational_efficiency": 21,
                        "total": 81,
                        "rationale": "Best fit for multi-segment brand",
                    },
                ],
                "why_not_others": [],
                "confidence_score": 0.82,
                "citations": ["Market analysis data"],
            },
            "hierarchy": {
                "root": {
                    "name": "TestBrand",
                    "type": "master",
                    "relationship_to_parent": "root",
                    "children": [
                        {
                            "name": "TestProduct",
                            "type": "product_line",
                            "relationship_to_parent": "product_line_of",
                            "children": [],
                        },
                    ],
                },
                "total_depth": 2,
                "total_nodes": 2,
            },
            "naming_hierarchy": {
                "naming_pattern": "Prefix: Parent + Descriptor",
                "naming_rules": [{"rule": "Use parent name as prefix"}],
                "consistency_score": 85,
            },
            "growth_path": {
                "phases": [
                    {"phase": 1, "timeline": "0-6 months", "actions": ["Launch core"]},
                ],
                "portfolio_risk_assessment": [
                    {"risk": "Brand dilution", "severity": "medium"},
                ],
            },
            "strategy": {"executive_summary": "Hybrid architecture recommended"},
            "confidence_score": 0.82,
            "findings": ["Multi-segment audience favors hybrid model"],
            "recommendations": ["Adopt hybrid architecture"],
            "sources": [{"source": "Market analysis"}],
        }
    )
    return llm


@pytest.fixture
def mock_events():
    return AsyncMock(spec=EventEmitter)


@pytest.fixture
def analyzer(mock_llm, mock_events):
    return BAAAnalyzer(anthropic_client=mock_llm, event_emitter=mock_events)


class TestBAAAnalyzer:
    """Test BAAAnalyzer behavior."""

    async def test_analyze_returns_complete_result(self, analyzer):
        result = await analyzer.analyze(
            prompt="Design architecture for TestBrand",
            tenant_id="test-tenant",
            user_role="EDITOR",
            config={},
            previous_outputs={},
            wf1_context={"mra": {}, "cia": {}},
            bpa_context={"recommended_positioning": {"statement": "test"}},
            company_context={"name": "TestCorp"},
        )
        assert result["query"] == "Design architecture for TestBrand"
        assert result["confidence_score"] == 0.82
        assert result["wf1_context_used"] is True
        assert result["bpa_context_used"] is True
        assert result["execution_time_ms"] >= 0

    async def test_analyze_returns_recommendation(self, analyzer):
        result = await analyzer.analyze(
            prompt="Test",
            tenant_id="t",
            user_role="EDITOR",
            config={},
            previous_outputs={},
            wf1_context={"mra": {}},
            bpa_context={"recommended_positioning": {}},
            company_context={},
        )
        rec = result["recommendation"]
        assert rec["recommended_model"] == "hybrid"

    async def test_analyze_returns_hierarchy(self, analyzer):
        result = await analyzer.analyze(
            prompt="Test",
            tenant_id="t",
            user_role="EDITOR",
            config={},
            previous_outputs={},
            wf1_context={},
            bpa_context={},
            company_context={},
        )
        hierarchy = result["hierarchy"]
        assert hierarchy["root"]["name"] == "TestBrand"

    async def test_stub_result_when_no_llm(self, mock_events):
        analyzer = BAAAnalyzer(anthropic_client=None, event_emitter=mock_events)
        result = await analyzer.analyze(
            prompt="Test",
            tenant_id="t",
            user_role="EDITOR",
            config={},
            previous_outputs={},
            wf1_context={},
            bpa_context={},
            company_context={},
        )
        assert result["confidence_score"] == 0.0
        assert "LLM unavailable" in result["findings"][0]

    async def test_merge_context_wf1_and_bpa(self, analyzer):
        context = analyzer._merge_context(
            wf1_context={"mra": {"tam": "$10B"}, "cia": {"competitors": ["A"]}},
            bpa_context={"recommended_positioning": {"statement": "test"}},
            company_context={"name": "TestCorp"},
            previous_outputs={},
        )
        assert context["mra"]["tam"] == "$10B"
        assert context["bpa"]["recommended_positioning"]["statement"] == "test"
        assert context["company"]["name"] == "TestCorp"

    async def test_merge_context_previous_outputs_override(self, analyzer):
        context = analyzer._merge_context(
            wf1_context={"mra": {"tam": "$5B"}},
            bpa_context={},
            company_context={},
            previous_outputs={
                "market_research": {"tam": "$10B"},
                "brand_positioning": {
                    "recommended_positioning": {"statement": "override"}
                },
            },
        )
        assert context["mra"]["tam"] == "$10B"  # previous_outputs takes precedence
        assert context["bpa"]["recommended_positioning"]["statement"] == "override"
