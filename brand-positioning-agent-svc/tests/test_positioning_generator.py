"""Tests for PositioningGenerator (SKL-BPA-06)."""

import pytest

from app.logic.positioning_generator import PositioningGenerator


class TestPositioningGenerator:
    """Test positioning generation logic."""

    async def test_generate_default_count(self):
        gen = PositioningGenerator()
        result = await gen.generate(
            context={"mra": {"market": "test"}, "cia": {"competitors": []}},
            candidate_count=3,
        )
        assert len(result) == 3
        assert result[0]["framework"] == "classic"

    async def test_generate_single_candidate(self):
        gen = PositioningGenerator()
        result = await gen.generate(context={}, candidate_count=1)
        assert len(result) == 1
        assert result[0]["framework"] == "classic"

    async def test_generate_max_candidates(self):
        gen = PositioningGenerator()
        result = await gen.generate(context={}, candidate_count=5)
        assert len(result) == 5

    async def test_context_summary_includes_available_data(self):
        gen = PositioningGenerator()
        result = await gen.generate(
            context={
                "mra": {"data": True},
                "cia": {"data": True},
                "apa": {"data": True},
            },
            candidate_count=1,
        )
        summary = result[0]["context_summary"]
        assert "Market research" in summary
        assert "Competitive intelligence" in summary
        assert "Audience personas" in summary
