"""Tests for OG-07: Hybrid defamation guard — keyword filter + scrubbing."""

from app.logic.guardrails import (
    OutputGuardrails,
    _defamation_keyword_score,
    _scrub_defamatory_content,
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


class TestDefamationKeywordScore:
    def test_clean_text_zero_score(self):
        score = _defamation_keyword_score("Acme Corp is a market leader")
        assert score == 0.0

    def test_single_keyword_low_score(self):
        score = _defamation_keyword_score("There are fraud allegations")
        assert 0.0 < score <= 0.2

    def test_multiple_keywords_high_score(self):
        score = _defamation_keyword_score(
            "This company is a fraud, involved in criminal corruption and embezzlement"
        )
        assert score > 0.3

    def test_empty_text(self):
        assert _defamation_keyword_score("") == 0.0

    def test_case_insensitive(self):
        score = _defamation_keyword_score("FRAUD and SCAM detected")
        assert score > 0.0


class TestDefamationScrubbing:
    def test_scrub_fraud_claim(self):
        text = "Acme Corp is a fraud in the market"
        result = _scrub_defamatory_content(text)
        assert "alleged" in result.lower()

    def test_scrub_known_to_cheat(self):
        text = "The CEO is known to cheat customers"
        result = _scrub_defamatory_content(text)
        assert "alleged" in result.lower()

    def test_clean_text_unchanged(self):
        text = "Acme Corp is a market leader with strong products"
        result = _scrub_defamatory_content(text)
        assert result == text

    def test_empty_string(self):
        assert _scrub_defamatory_content("") == ""


class TestDefamationGuard:
    def setup_method(self):
        self.guardrails = OutputGuardrails()

    async def test_defamatory_findings_flagged(self):
        response = _make_response(
            findings=[
                "Acme Corp is a fraud involved in criminal corruption and embezzlement"
            ]
        )
        await self.guardrails.evaluate(response)
        assert "Defamation risk - claims require verification" in response.methodology_notes

    async def test_clean_findings_not_flagged(self):
        response = _make_response(
            findings=["Acme Corp has 15% market share in the SaaS space"]
        )
        await self.guardrails.evaluate(response)
        assert "Defamation risk - claims require verification" not in response.methodology_notes

    async def test_defamatory_executive_summary_flagged(self):
        response = _make_response(
            executive_summary="The company is a known scam with criminal fraud"
        )
        await self.guardrails.evaluate(response)
        assert "Defamation risk - claims require verification" in response.methodology_notes

    async def test_borderline_not_flagged(self):
        response = _make_response(
            findings=["Some users reported fraud concerns"]
        )
        await self.guardrails.evaluate(response)
        # Single keyword "fraud" scores 0.1 which is below 0.3 threshold
        assert "Defamation risk - claims require verification" not in response.methodology_notes
