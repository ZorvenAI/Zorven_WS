"""Tests for BSA API schemas."""

import pytest

from app.api.schemas import ExecuteRequest, BSAResponse


class TestExecuteRequest:
    """Test ExecuteRequest schema."""

    def test_minimal_request(self):
        req = ExecuteRequest(input_prompt="Tell a brand story")
        assert req.input_prompt == "Tell a brand story"
        assert req.input_context == {}
        assert req.tenant_context == {}

    def test_full_request(self):
        req = ExecuteRequest(
            input_prompt="Create brand story",
            input_context={"company_name": "TestCo"},
            tenant_context={"tenant_id": "t1"},
            config={"temperature": 0.7},
            previous_outputs={"brand_naming": {"confidence_score": 0.85}},
        )
        assert req.input_context["company_name"] == "TestCo"
        assert req.previous_outputs["brand_naming"]["confidence_score"] == 0.85

    def test_empty_prompt_allowed(self):
        req = ExecuteRequest(input_prompt="")
        assert req.input_prompt == ""


class TestBSAResponse:
    """Test BSAResponse schema."""

    def test_minimal_response(self):
        resp = BSAResponse(
            query="brand story",
            origin_story={},
            mission_vision={},
            pitches={},
            channel_narratives={},
            story_style_guide={},
            narrative_package={},
            confidence_score=0.0,
        )
        assert resp.confidence_score == 0.0
        assert resp.origin_story == {}

    def test_full_response(self):
        resp = BSAResponse(
            query="Create brand story for TestBrand",
            origin_story={
                "archetype_used": "Hero",
                "versions": [{"version_label": "short", "content": "Story..."}],
            },
            mission_vision={
                "mission": {"recommended": "Our mission"},
                "vision": {"recommended": "Our vision"},
            },
            pitches={
                "pitch_30s": {"content": "30s pitch", "memorability_score": 0.82},
            },
            channel_narratives={
                "website_about": {"content": "About us"},
                "channel_consistency_score": 0.85,
            },
            story_style_guide={
                "narrative_principles": ["Be authentic"],
            },
            narrative_package={
                "overall_confidence": 0.81,
                "summary": "Brand story summary",
            },
            subbrand_stories=[{"sub_brand": "Sub1"}],
            wf2_strategy_summary={"positioning": "Leader"},
            confidence_score=0.81,
            findings=["Finding 1"],
            recommendations=["Recommendation 1"],
            execution_time_ms=4200.0,
        )
        assert resp.confidence_score == 0.81
        assert resp.execution_time_ms == 4200.0
        assert len(resp.subbrand_stories) == 1
