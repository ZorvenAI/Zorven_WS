"""Tests for AakerProfiler logic module."""

import pytest

from app.logic.aaker_profiler import AakerProfiler


@pytest.fixture
def profiler():
    return AakerProfiler()


class TestAakerProfiler:

    async def test_validate_clamps_scores(self, profiler):
        profile = {
            "dimensions": [
                {"dimension": "Sincerity", "score": 120, "rationale": ""},
                {"dimension": "Excitement", "score": -10, "rationale": ""},
                {"dimension": "Competence", "score": 85, "rationale": ""},
            ],
        }
        result = await profiler.validate(profile)
        scores = {d["dimension"]: d["score"] for d in result["dimensions"]}
        assert scores["Sincerity"] == 100  # clamped to max
        assert scores["Excitement"] == 0  # clamped to min
        assert scores["Competence"] == 85

    async def test_validate_ensures_all_dimensions(self, profiler):
        profile = {
            "dimensions": [
                {"dimension": "Sincerity", "score": 50, "rationale": ""},
            ],
        }
        result = await profiler.validate(profile)
        dims = {d["dimension"] for d in result["dimensions"]}
        assert "Sincerity" in dims
        assert "Excitement" in dims
        assert "Competence" in dims
        assert "Sophistication" in dims
        assert "Ruggedness" in dims

    async def test_validate_identifies_primary_secondary(self, profiler):
        profile = {
            "dimensions": [
                {"dimension": "Sincerity", "score": 30, "rationale": ""},
                {"dimension": "Excitement", "score": 90, "rationale": ""},
                {"dimension": "Competence", "score": 80, "rationale": ""},
                {"dimension": "Sophistication", "score": 50, "rationale": ""},
                {"dimension": "Ruggedness", "score": 20, "rationale": ""},
            ],
        }
        result = await profiler.validate(profile)
        # LLM's choice not provided, so auto-detect
        assert result["primary_dimension"] == "Excitement"
        assert result["secondary_dimension"] == "Competence"

    async def test_validate_respects_llm_choice(self, profiler):
        profile = {
            "dimensions": [
                {"dimension": "Sincerity", "score": 80, "rationale": ""},
                {"dimension": "Excitement", "score": 90, "rationale": ""},
            ],
            "primary_dimension": "Sincerity",
            "secondary_dimension": "Excitement",
        }
        result = await profiler.validate(profile)
        assert result["primary_dimension"] == "Sincerity"
        assert result["secondary_dimension"] == "Excitement"

    async def test_validate_empty_profile(self, profiler):
        result = await profiler.validate({})
        assert len(result["dimensions"]) == 5  # all dimensions added
        assert result["differentiation_score"] == 0.0
