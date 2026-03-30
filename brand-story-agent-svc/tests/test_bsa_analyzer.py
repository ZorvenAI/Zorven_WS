"""Tests for BSAAnalyzer."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.bsa_analyzer import BSAAnalyzer


@pytest.fixture
def mock_llm():
    """Mock AnthropicClient with generate_json method."""
    llm = AsyncMock()
    llm.generate_json = AsyncMock(return_value={"stub": True})
    return llm


@pytest.fixture
def analyzer(mock_llm):
    """Create analyzer with mocked LLM client."""
    mock_event_emitter = AsyncMock()
    mock_event_emitter.emit = AsyncMock()

    return BSAAnalyzer(
        anthropic_client=mock_llm,
        event_emitter=mock_event_emitter,
    )


class TestBSAAnalyzer:
    """Test BSAAnalyzer."""

    async def test_analyze_returns_result(self, analyzer, mock_llm):
        narrative_response = {
            "origin_story": {
                "archetype_used": "Hero",
                "emotional_arc": "tension-transformation-resolution",
                "versions": [
                    {
                        "version_label": "short",
                        "word_count": 480,
                        "content": "The story of TestBrand...",
                        "archetype_arc_alignment": 0.85,
                        "emotional_resonance_score": 0.80,
                        "voice_consistency_score": 0.78,
                    },
                ],
            },
            "mission_vision": {
                "mission": {
                    "recommended": "To empower innovators",
                    "scores": {"clarity": 0.88, "positioning_alignment": 0.82},
                },
                "vision": {
                    "recommended": "A world where...",
                    "scores": {"inspiration": 0.85},
                },
            },
            "pitches": {
                "pitch_30s": {
                    "content": "30s pitch",
                    "word_count": 75,
                    "memorability_score": 0.82,
                },
            },
            "findings": ["Key finding 1"],
            "recommendations": ["Rec 1"],
        }

        synthesis_response = {
            "channel_narratives": {
                "website_about": {
                    "channel": "website",
                    "tone": "warm",
                    "content": "About us page",
                },
                "channel_consistency_score": 0.85,
            },
            "story_style_guide": {
                "narrative_principles": ["Be authentic"],
            },
            "narrative_package": {
                "overall_confidence": 0.82,
                "positioning_narrative_alignment": 0.79,
                "summary": "TestBrand narrative summary",
            },
            "findings": [],
            "recommendations": [],
            "confidence_score": 0.82,
        }

        mock_llm.generate_json = AsyncMock(
            side_effect=[narrative_response, synthesis_response]
        )

        result = await analyzer.analyze(
            prompt="Create brand story for TestBrand",
            tenant_id="test-tenant",
            user_role="EDITOR",
            config={},
            previous_outputs={},
            wf1_context={"personas": [{"slug": "early-adopter"}]},
            bpa_context={
                "recommended_positioning": {"statement": "The most reliable brand"}
            },
            bpv_context={"archetype": {"primary": {"name": "Hero"}}},
            nta_context={
                "naming_brief": {
                    "recommended_name": "TestBrand",
                    "recommended_tagline": "Be amazing",
                }
            },
            company_context={"name": "TestCo", "industry": "Technology"},
            baa_context=None,
            job_id="test-job-123",
        )

        assert "origin_story" in result
        assert "mission_vision" in result
        assert "pitches" in result
        assert "channel_narratives" in result
        assert "narrative_package" in result

    async def test_analyze_stub_result_when_no_llm(self):
        """Analyzer should return stub result when no LLM client."""
        mock_event_emitter = AsyncMock()
        mock_event_emitter.emit = AsyncMock()

        analyzer = BSAAnalyzer(
            anthropic_client=None,
            event_emitter=mock_event_emitter,
        )

        result = await analyzer.analyze(
            prompt="Create brand story",
            tenant_id="test-tenant",
            user_role="EDITOR",
            config={},
            previous_outputs={},
            wf1_context=None,
            bpa_context=None,
            bpv_context=None,
            nta_context=None,
            company_context=None,
            job_id="test-job",
        )

        assert result is not None
        assert "origin_story" in result
        assert "confidence_score" in result

    async def test_analyze_makes_two_claude_calls(self, analyzer, mock_llm):
        """Analyzer should make exactly 2 Claude API calls."""
        mock_llm.generate_json = AsyncMock(
            return_value={
                "origin_story": {"versions": []},
                "mission_vision": {},
                "pitches": {},
                "channel_narratives": {},
                "story_style_guide": {},
                "narrative_package": {},
                "findings": [],
                "recommendations": [],
                "confidence_score": 0.5,
            }
        )

        await analyzer.analyze(
            prompt="Create brand story",
            tenant_id="test-tenant",
            user_role="EDITOR",
            config={},
            previous_outputs={},
            wf1_context=None,
            bpa_context={"recommended_positioning": {"statement": "Leader"}},
            bpv_context={"archetype": {"primary": {"name": "Hero"}}},
            nta_context=None,
            company_context={"name": "TestCo"},
            job_id="test-job",
        )

        assert mock_llm.generate_json.await_count == 2
