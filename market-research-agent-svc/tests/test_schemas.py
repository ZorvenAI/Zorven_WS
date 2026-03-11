"""Tests for Pydantic v2 schemas."""

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    ExecuteRequest,
    HealthResponse,
    MarketResearchResponse,
    SourceItem,
    TenantContext,
)


class TestTenantContext:
    def test_defaults(self):
        ctx = TenantContext()
        assert ctx.tenant_id == ""
        assert ctx.gcs_raw_bucket == ""

    def test_with_values(self):
        ctx = TenantContext(tenant_id="t1", rag_data_store_id="ds-1")
        assert ctx.tenant_id == "t1"
        assert ctx.rag_data_store_id == "ds-1"


class TestExecuteRequest:
    def test_requires_input_prompt(self):
        with pytest.raises(ValidationError):
            ExecuteRequest()

    def test_minimal(self):
        req = ExecuteRequest(input_prompt="test")
        assert req.input_prompt == "test"
        assert req.config == {}
        assert req.previous_outputs == {}

    def test_full_payload(self):
        req = ExecuteRequest(
            input_prompt="market analysis",
            input_context={"company_id": 1},
            tenant_context={"tenant_id": "t1"},
            config={"focus": "sizing"},
            previous_outputs={"web_research": {"findings": []}},
        )
        assert req.input_prompt == "market analysis"
        assert req.config["focus"] == "sizing"


class TestSourceItem:
    def test_defaults(self):
        s = SourceItem()
        assert s.type == "web"
        assert s.title == ""
        assert s.url == ""

    def test_with_values(self):
        s = SourceItem(
            type="economic_data", title="GDP Data", url="https://data.worldbank.org"
        )
        assert s.type == "economic_data"


class TestMarketResearchResponse:
    def test_defaults(self):
        r = MarketResearchResponse()
        assert r.query == ""
        assert r.market_overview == ""
        assert r.market_sizing == {}
        assert r.competitive_landscape == []
        assert r.industry_trends == []
        assert r.economic_indicators == {}
        assert r.sources == []
        assert r.findings == []
        assert r.recommendations == []
        assert r.raw_context == ""
        assert r.confidence_score == 0.0
        assert r.methodology_notes == []

    def test_full_response(self):
        r = MarketResearchResponse(
            query="test",
            market_overview="Overview here",
            market_sizing={"tam": "$100B", "sam": "$10B", "som": "$1B"},
            competitive_landscape=[{"name": "Acme", "market_position": "leader"}],
            industry_trends=["AI adoption growing"],
            economic_indicators={"gdp": {"latest_value": 1000}},
            sources=[SourceItem(type="web", title="Test", url="https://example.com")],
            findings=["Market is growing"],
            recommendations=["Invest in AI"],
            confidence_score=0.85,
            methodology_notes=["Top-down TAM estimation"],
        )
        assert r.confidence_score == 0.85
        assert len(r.sources) == 1
        assert r.market_sizing["tam"] == "$100B"


class TestHealthResponse:
    def test_defaults(self):
        h = HealthResponse()
        assert h.status == "ok"
        assert h.version == "0.1.0"
