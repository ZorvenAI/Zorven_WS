"""Tests for NTAAnalyzer — 5-phase PAOR engine."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.messaging.event_emitter import EventEmitter, EventType
from app.services.nta_analyzer import NTAAnalyzer


@pytest.fixture
def event_emitter():
    emitter = AsyncMock(spec=EventEmitter)
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def mock_llm():
    """Mock AnthropicClient returning configurable JSON."""
    llm = AsyncMock()
    # First call (name generation) returns candidates
    name_response = {
        "name_candidates": [
            {
                "name": "Voltara",
                "rationale": "Evocative of voltage + aura",
                "naming_type": "coined",
                "scores": {
                    "linguistic": 82,
                    "memorability": 88,
                    "strategy_alignment": 75,
                },
            },
            {
                "name": "ChargeLine",
                "rationale": "Descriptive of charging lines",
                "naming_type": "descriptive",
                "scores": {
                    "linguistic": 70,
                    "memorability": 65,
                    "strategy_alignment": 80,
                },
            },
        ],
        "findings": ["Strong coined options identified"],
        "recommendations": ["Consider domain alternatives for ChargeLine"],
        "sources": [{"type": "analysis"}],
        "confidence_score": 0.8,
    }
    # Second call (tagline synthesis) returns taglines + brief
    tagline_response = {
        "taglines": [
            {
                "tagline": "Power Every Journey",
                "name": "Voltara",
                "emotional_appeal": "Empowerment",
                "memorability_score": 85,
            },
        ],
        "naming_brief": {
            "recommended_name": "Voltara",
            "recommended_tagline": "Power Every Journey",
            "rationale": "Strong coined name with high memorability",
        },
        "confidence_score": 0.82,
        "findings": [],
        "recommendations": [],
        "sources": [],
    }
    llm.generate_json = AsyncMock(
        side_effect=[name_response, tagline_response]
    )
    return llm


@pytest.fixture
def analyzer(mock_llm, event_emitter):
    return NTAAnalyzer(
        anthropic_client=mock_llm,
        event_emitter=event_emitter,
    )


@pytest.fixture
def full_context():
    return {
        "market_research": {"market_overview": "EV market growing"},
        "brand_positioning": {
            "recommended_positioning": {"statement": "Most reliable"},
        },
        "brand_personality": {
            "aaker_profile": {"primary_dimension": "Competence"},
        },
    }


class TestAnalyzerFullFlow:
    """Test the full 5-phase analysis flow."""

    @patch("app.services.nta_analyzer.DomainChecker")
    @patch("app.services.nta_analyzer.SocialHandleChecker")
    @patch("app.services.nta_analyzer.TrademarkSearcher")
    async def test_full_analysis_returns_expected_keys(
        self, MockTrademark, MockSocial, MockDomain,
        analyzer, full_context, mock_llm,
    ):
        # Mock availability checks
        MockDomain.return_value.check = AsyncMock(
            return_value={".com": True, ".io": True, ".co": None}
        )
        MockSocial.return_value.check = AsyncMock(
            return_value={"twitter": True, "instagram": False, "linkedin": None}
        )
        MockTrademark.return_value.search = AsyncMock(
            return_value={"clear": True, "conflicts": [], "notes": ""}
        )

        # Re-create analyzer with patched skills
        analyzer._domain_checker = MockDomain.return_value
        analyzer._social_checker = MockSocial.return_value
        analyzer._trademark_searcher = MockTrademark.return_value

        result = await analyzer.analyze(
            prompt="Create brand names for EV charging",
            tenant_id="t1",
            user_role="EDITOR",
            config={},
            previous_outputs=full_context,
            wf1_context=None,
            bpa_context=None,
            bpv_context=None,
            company_context=None,
        )

        assert "name_candidates" in result
        assert "shortlisted_names" in result
        assert "taglines" in result
        assert "naming_brief" in result
        assert "availability_results" in result
        assert "scoring_summary" in result
        assert "confidence_score" in result
        assert "execution_time_ms" in result

    @patch("app.services.nta_analyzer.DomainChecker")
    @patch("app.services.nta_analyzer.SocialHandleChecker")
    @patch("app.services.nta_analyzer.TrademarkSearcher")
    async def test_two_llm_calls_made(
        self, MockTrademark, MockSocial, MockDomain,
        analyzer, full_context, mock_llm,
    ):
        """Analyzer must make exactly 2 Claude calls (name gen + tagline)."""
        MockDomain.return_value.check = AsyncMock(
            return_value={".com": True}
        )
        MockSocial.return_value.check = AsyncMock(
            return_value={"twitter": True}
        )
        MockTrademark.return_value.search = AsyncMock(
            return_value={"clear": True, "conflicts": [], "notes": ""}
        )

        analyzer._domain_checker = MockDomain.return_value
        analyzer._social_checker = MockSocial.return_value
        analyzer._trademark_searcher = MockTrademark.return_value

        await analyzer.analyze(
            prompt="Names please",
            tenant_id="t1",
            user_role="EDITOR",
            config={},
            previous_outputs=full_context,
            wf1_context=None,
            bpa_context=None,
            bpv_context=None,
            company_context=None,
        )

        assert mock_llm.generate_json.call_count == 2


class TestMergeContext:
    """Test context merging logic."""

    async def test_previous_outputs_override_context(self, analyzer):
        merged = analyzer._merge_context(
            wf1_context={"mra": {"old": True}},
            bpa_context={"old_bpa": True},
            bpv_context={"old_bpv": True},
            company_context={"name": "OldCo"},
            baa_context=None,
            previous_outputs={
                "market_research": {"new": True},
                "brand_positioning": {"new_bpa": True},
                "brand_personality": {"new_bpv": True},
            },
        )
        assert merged["mra"] == {"new": True}
        assert merged["bpa"] == {"new_bpa": True}
        assert merged["bpv"] == {"new_bpv": True}

    async def test_context_flags(self, analyzer):
        merged = analyzer._merge_context(
            wf1_context={"mra": {"data": True}},
            bpa_context={"pos": True},
            bpv_context={"pers": True},
            company_context=None,
            baa_context={"arch": True},
            previous_outputs={},
        )
        assert "mra" in merged
        assert "bpa" in merged
        assert "bpv" in merged
        assert "baa" in merged

    async def test_empty_context(self, analyzer):
        merged = analyzer._merge_context(
            None, None, None, None, None, {}
        )
        assert merged.get("company") == {}
        assert "mra" not in merged


class TestStubResult:
    """Test stub result when LLM unavailable."""

    async def test_stub_when_no_llm(self, event_emitter):
        analyzer = NTAAnalyzer(
            anthropic_client=None,
            event_emitter=event_emitter,
        )
        result = await analyzer.analyze(
            prompt="test",
            tenant_id="t1",
            user_role="EDITOR",
            config={},
            previous_outputs={
                "brand_positioning": {},
                "brand_personality": {},
            },
            wf1_context=None,
            bpa_context=None,
            bpv_context=None,
            company_context=None,
        )
        assert result["name_candidates"] == []
        assert "LLM unavailable" in result["findings"][0]
