"""Tests for PerceptualMapper (SKL-BPA-08)."""

import pytest

from app.logic.perceptual_mapper import PerceptualMapper


class TestPerceptualMapper:
    """Test perceptual map generation."""

    async def test_generate_default_maps(self):
        mapper = PerceptualMapper()
        result = await mapper.generate(
            competitive_data={"competitors": ["A", "B"]},
            map_count=3,
        )
        assert len(result) == 3
        assert result[0]["is_primary_recommended"] is True
        assert result[1]["is_primary_recommended"] is False

    async def test_generate_single_map(self):
        mapper = PerceptualMapper()
        result = await mapper.generate(
            competitive_data={},
            map_count=1,
        )
        assert len(result) == 1
        assert result[0]["map_id"].startswith("pm-")

    async def test_generate_max_maps(self):
        mapper = PerceptualMapper()
        result = await mapper.generate(
            competitive_data={},
            map_count=5,
        )
        assert len(result) == 5

    async def test_map_has_required_fields(self):
        mapper = PerceptualMapper()
        result = await mapper.generate(
            competitive_data={},
            map_count=1,
        )
        m = result[0]
        assert "map_id" in m
        assert "dimension_x" in m
        assert "dimension_y" in m
        assert "entities" in m
        assert "migration_vector" in m
        assert "white_space_highlighted" in m
        assert "differentiation_potential_score" in m
