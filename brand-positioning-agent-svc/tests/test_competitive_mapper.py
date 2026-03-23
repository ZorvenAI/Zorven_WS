"""Tests for CompetitiveMapper (SKL-BPA-01)."""

import pytest

from app.logic.competitive_mapper import CompetitiveMapper


class TestCompetitiveMapper:
    """Test competitive mapping logic."""

    async def test_map_with_competitors(self):
        mapper = CompetitiveMapper()
        result = await mapper.map(
            {
                "competitors_analyzed": ["Company A", "Company B"],
                "positioning_gaps": [
                    {"dimension": "Price", "opportunity_score": 8},
                ],
                "swot_analysis": {"strengths": ["Strong brand"]},
            }
        )
        assert result["competitor_count"] == 2
        assert len(result["positioning_gaps"]) == 1
        assert result["competitive_dimensions"]

    async def test_map_with_empty_data(self):
        mapper = CompetitiveMapper()
        result = await mapper.map({})
        assert result["competitor_count"] == 0
        assert result["competitive_dimensions"]

    async def test_map_falls_back_to_competitors_key(self):
        mapper = CompetitiveMapper()
        result = await mapper.map(
            {
                "competitors": [
                    {"name": "Rival A"},
                    {"name": "Rival B"},
                ],
            }
        )
        assert result["competitor_count"] == 2
