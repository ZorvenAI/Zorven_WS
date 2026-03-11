"""Tests for input/output guardrails."""

import pytest
from fastapi import HTTPException

from app.api.schemas import MarketResearchResponse, SourceItem
from app.logic.guardrails import InputGuardrail, OutputGuardrail


class TestInputGuardrail:
    def setup_method(self):
        self.guard = InputGuardrail()

    def test_valid_prompt_passes(self):
        result = self.guard.validate("What is the market size for AI tools?")
        assert "market size" in result

    def test_empty_prompt_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            self.guard.validate("")
        assert exc_info.value.status_code == 400

    def test_whitespace_only_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            self.guard.validate("   ")
        assert exc_info.value.status_code == 400

    def test_too_long_prompt_raises_400(self):
        long_prompt = "a" * 5001
        with pytest.raises(HTTPException) as exc_info:
            self.guard.validate(long_prompt)
        assert exc_info.value.status_code == 400

    def test_max_length_prompt_passes(self):
        prompt = "a" * 5000
        result = self.guard.validate(prompt)
        assert len(result) == 5000

    def test_ssn_detected_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            self.guard.validate("Research market for 123-45-6789")
        assert exc_info.value.status_code == 400
        assert "SSN" in exc_info.value.detail

    def test_credit_card_detected_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            self.guard.validate("Market analysis 4111-1111-1111-1111")
        assert exc_info.value.status_code == 400
        assert "credit card" in exc_info.value.detail

    def test_whitespace_normalized(self):
        result = self.guard.validate("market   size   analysis")
        assert result == "market size analysis"


class TestOutputGuardrail:
    def setup_method(self):
        self.guard = OutputGuardrail()

    def test_valid_response_passes(self):
        response = MarketResearchResponse(
            query="test",
            findings=["Market growing at 15% CAGR"],
            confidence_score=0.8,
        )
        result = self.guard.validate(response)
        assert result.confidence_score == 0.8

    def test_clamps_negative_confidence(self):
        response = MarketResearchResponse(confidence_score=-0.5)
        result = self.guard.validate(response)
        assert result.confidence_score == 0.0

    def test_clamps_over_one_confidence(self):
        response = MarketResearchResponse(confidence_score=1.5)
        result = self.guard.validate(response)
        assert result.confidence_score == 1.0

    def test_strips_ssn_from_findings(self):
        response = MarketResearchResponse(
            findings=["Contact John at 123-45-6789 for details"],
        )
        result = self.guard.validate(response)
        assert "123-45-6789" not in result.findings[0]
        assert "[REDACTED-SSN]" in result.findings[0]

    def test_strips_credit_card_from_recommendations(self):
        response = MarketResearchResponse(
            recommendations=["Card 4111 1111 1111 1111 used for purchase"],
        )
        result = self.guard.validate(response)
        assert "4111 1111 1111 1111" not in result.recommendations[0]
        assert "[REDACTED-CC]" in result.recommendations[0]

    def test_empty_sources_logs_warning(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            response = MarketResearchResponse(sources=[])
            self.guard.validate(response)
        assert "no sources" in caplog.text.lower()

    def test_with_sources_no_warning(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            response = MarketResearchResponse(
                sources=[
                    SourceItem(type="web", title="Test", url="https://example.com")
                ]
            )
            self.guard.validate(response)
        assert "no sources" not in caplog.text.lower()
