"""Tests for BPVAnalyzer."""

import pytest
from unittest.mock import AsyncMock

from app.messaging.event_emitter import EventEmitter
from app.services.anthropic_client import AnthropicClient
from app.services.bpv_analyzer import BPVAnalyzer


@pytest.fixture
def mock_llm():
    llm = AsyncMock(spec=AnthropicClient)
    llm.generate_json = AsyncMock(
        return_value={
            "aaker_profile": {
                "dimensions": [
                    {"dimension": "Sincerity", "score": 60, "rationale": "Honest brand"},
                    {"dimension": "Excitement", "score": 80, "rationale": "Innovative"},
                    {"dimension": "Competence", "score": 85, "rationale": "Reliable"},
                    {"dimension": "Sophistication", "score": 45, "rationale": "Moderate"},
                    {"dimension": "Ruggedness", "score": 30, "rationale": "Low"},
                ],
                "primary_dimension": "Competence",
                "secondary_dimension": "Excitement",
                "differentiation_score": 35.0,
            },
            "archetype": {
                "primary": {
                    "name": "Sage",
                    "core_desire": "Truth",
                    "fear": "Ignorance",
                    "strategy": "Seek knowledge",
                    "gift": "Wisdom",
                    "shadow": "Dogmatism",
                    "brand_expression": "Expert authority",
                },
                "secondary": {
                    "name": "Creator",
                    "core_desire": "Innovation",
                },
                "resonance_score": 82.0,
                "blend_rationale": "Knowledge-driven innovation",
            },
            "values_hierarchy": {
                "core": [
                    {
                        "name": "Innovation",
                        "definition": "Pushing boundaries",
                        "behavioral_manifestation": "Always improving",
                    },
                    {
                        "name": "Reliability",
                        "definition": "Consistent quality",
                        "behavioral_manifestation": "Never fails",
                    },
                    {
                        "name": "Integrity",
                        "definition": "Honest dealings",
                        "behavioral_manifestation": "Transparent",
                    },
                ],
                "supporting": [
                    {
                        "name": "Sustainability",
                        "definition": "Eco-friendly",
                        "behavioral_manifestation": "Green practices",
                    },
                ],
                "aspirational": [
                    {
                        "name": "Market Leadership",
                        "definition": "Category leader",
                        "behavioral_manifestation": "Setting standards",
                    },
                ],
                "authenticity_score": 78.0,
            },
            "emotional_map": {
                "personas": [
                    {
                        "persona": "Fleet Manager",
                        "emotions": [
                            {"emotion": "trust", "intensity": 85},
                            {"emotion": "confidence", "intensity": 80},
                        ],
                    },
                ],
                "consistency_score": 82.0,
            },
            "voice_matrix": {
                "tone_spectrum": [
                    {"dimension": "formal-casual", "position": 35},
                ],
                "vocabulary": {"preferred": ["innovative"], "avoided": ["cheap"]},
                "style": {"formality": "professional"},
                "humor": {"type": "subtle", "frequency": "low"},
                "dos": ["Use data-driven language"],
                "donts": ["Use slang"],
                "channel_adaptations": [
                    {"channel": "LinkedIn", "adaptation": "Professional tone"},
                ],
            },
            "character_brief": {
                "persona_card": {
                    "name": "Dr. Volt",
                    "age": "45",
                    "personality": "Knowledgeable and reliable",
                },
                "executive_summary": "A competent, innovative brand personality",
                "positioning_alignment_score": 85.0,
            },
            "confidence_score": 0.82,
            "findings": ["Strong competence signal from brand voice"],
            "recommendations": ["Lean into Sage archetype"],
            "sources": [{"source": "Brand Discovery data"}],
        }
    )
    return llm


@pytest.fixture
def mock_events():
    return AsyncMock(spec=EventEmitter)


@pytest.fixture
def analyzer(mock_llm, mock_events):
    return BPVAnalyzer(anthropic_client=mock_llm, event_emitter=mock_events)


class TestBPVAnalyzer:
    """Test BPVAnalyzer behavior."""

    async def test_analyze_returns_complete_result(self, analyzer):
        result = await analyzer.analyze(
            prompt="Design brand personality for TestCorp",
            tenant_id="test-tenant",
            user_role="EDITOR",
            config={},
            previous_outputs={},
            wf1_context={"mra": {}, "apa": {}},
            bpa_context={"recommended_positioning": {"statement": "test"}},
            company_context={"name": "TestCorp", "brand_voice": "professional"},
        )
        assert result["query"] == "Design brand personality for TestCorp"
        assert result["confidence_score"] == 0.82
        assert result["wf1_context_used"] is True
        assert result["bpa_context_used"] is True
        assert result["execution_time_ms"] >= 0

    async def test_analyze_returns_aaker_profile(self, analyzer):
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
        aaker = result["aaker_profile"]
        assert aaker["primary_dimension"] == "Competence"
        assert len(aaker["dimensions"]) >= 5

    async def test_analyze_returns_archetype(self, analyzer):
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
        arch = result["archetype"]
        assert arch["primary"]["name"] == "Sage"

    async def test_stub_result_when_no_llm(self, mock_events):
        analyzer = BPVAnalyzer(anthropic_client=None, event_emitter=mock_events)
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
            baa_context=None,
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
            baa_context=None,
            previous_outputs={
                "market_research": {"tam": "$10B"},
                "brand_positioning": {
                    "recommended_positioning": {"statement": "override"}
                },
            },
        )
        assert context["mra"]["tam"] == "$10B"  # previous_outputs takes precedence
        assert context["bpa"]["recommended_positioning"]["statement"] == "override"
