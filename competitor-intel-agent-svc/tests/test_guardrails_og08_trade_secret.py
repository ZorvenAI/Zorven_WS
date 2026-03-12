"""Tests for OG-08: Trade secret shield — strip proprietary/confidential content."""

from app.logic.guardrails import (
    OutputGuardrails,
    _contains_trade_secret,
    _redact_trade_secret,
)


def _make_response(**overrides):
    from app.api.schemas import CompetitorIntelligenceResponse

    defaults = {
        "query": "test",
        "competitors_analyzed": [],
        "swot_analyses": [],
        "positioning_gaps": [],
        "executive_summary": "test summary",
        "findings": [],
        "recommendations": [],
        "sources": [{"type": "web", "title": "src", "url": "https://example.com"}],
        "confidence_score": 0.85,
        "methodology_notes": [],
        "raw_context": "",
    }
    defaults.update(overrides)
    return CompetitorIntelligenceResponse(**defaults)


class TestTradeSecretDetection:
    def test_proprietary_detected(self):
        assert _contains_trade_secret("This is proprietary information about Acme")

    def test_confidential_detected(self):
        assert _contains_trade_secret("Confidential pricing data for competitor")

    def test_trade_secret_detected(self):
        assert _contains_trade_secret("This contains trade secret details")

    def test_internal_only_detected(self):
        assert _contains_trade_secret("This document is internal only")

    def test_nda_detected(self):
        assert _contains_trade_secret("Covered under NDA agreement")

    def test_source_code_detected(self):
        assert _contains_trade_secret("Leaked source code from competitor repo")

    def test_salary_data_detected(self):
        assert _contains_trade_secret("Salary data shows average engineer pay")

    def test_unreleased_product_detected(self):
        assert _contains_trade_secret("Unreleased product feature roadmap")

    def test_clean_text_not_detected(self):
        assert not _contains_trade_secret("Acme Corp has 500 employees and $50M revenue")

    def test_empty_string(self):
        assert not _contains_trade_secret("")


class TestTradeSecretRedaction:
    def test_proprietary_redacted(self):
        result = _redact_trade_secret("This is proprietary data about pricing")
        assert "[REDACTED-PROPRIETARY]" in result
        assert "proprietary" not in result.lower().replace("[redacted-proprietary]", "")

    def test_multiple_patterns_redacted(self):
        result = _redact_trade_secret(
            "Confidential trade secret internal only document"
        )
        assert result.count("[REDACTED-PROPRIETARY]") >= 2

    def test_clean_text_unchanged(self):
        text = "Acme Corp is a market leader in SaaS"
        assert _redact_trade_secret(text) == text


class TestTradeSecretShield:
    def setup_method(self):
        self.guardrails = OutputGuardrails()

    async def test_trade_secret_in_findings_stripped(self):
        response = _make_response(
            findings=["Competitor has proprietary algorithm for pricing"]
        )
        await self.guardrails.evaluate(response)
        assert "[REDACTED-PROPRIETARY]" in response.findings[0]
        assert "Trade secret content stripped" in response.methodology_notes

    async def test_trade_secret_in_executive_summary_stripped(self):
        response = _make_response(
            executive_summary="Based on confidential internal documents"
        )
        await self.guardrails.evaluate(response)
        assert "[REDACTED-PROPRIETARY]" in response.executive_summary

    async def test_trade_secret_in_raw_context_stripped(self):
        response = _make_response(
            raw_context="This source code was leaked from internal systems"
        )
        await self.guardrails.evaluate(response)
        assert "[REDACTED-PROPRIETARY]" in response.raw_context

    async def test_clean_response_not_flagged(self):
        response = _make_response(
            findings=["Acme Corp has 15% market share"],
            executive_summary="Standard competitive analysis",
        )
        await self.guardrails.evaluate(response)
        assert "Trade secret content stripped" not in response.methodology_notes

    async def test_recommendations_also_checked(self):
        response = _make_response(
            recommendations=["Exploit their trade secret pricing model"]
        )
        await self.guardrails.evaluate(response)
        assert "[REDACTED-PROPRIETARY]" in response.recommendations[0]
