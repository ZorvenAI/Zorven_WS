"""Tests for ModelRecommender logic module."""

import pytest

from app.logic.model_recommender import ModelRecommender


@pytest.fixture
def recommender():
    return ModelRecommender()


class TestModelRecommender:

    async def test_recommend_validates_scores(self, recommender):
        llm_result = {
            "recommendation": {
                "recommended_model": "branded_house",
                "model_scores": [
                    {
                        "model": "branded_house",
                        "positioning_alignment": 30,  # over max
                        "audience_fit": -5,  # under min
                        "competitive_diff": 20,
                        "operational_efficiency": 22,
                        "total": 110,  # over max
                        "rationale": "Test",
                    },
                ],
                "confidence_score": 0.8,
            }
        }
        result = await recommender.recommend({}, llm_result)
        scores = result["model_scores"][0]
        assert scores["positioning_alignment"] == 25  # clamped to max
        assert scores["audience_fit"] == 0  # clamped to min
        assert scores["total"] == 100  # clamped to max

    async def test_recommend_empty_result(self, recommender):
        result = await recommender.recommend({}, {})
        assert result["recommended_model"] == "hybrid"  # default
        assert result["model_scores"] == []
