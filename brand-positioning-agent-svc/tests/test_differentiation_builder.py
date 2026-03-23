"""Tests for DifferentiationBuilder (SKL-BPA-09)."""

import pytest

from app.logic.differentiation_builder import DifferentiationBuilder


class TestDifferentiationBuilder:
    """Test differentiation framework building."""

    async def test_build_with_data(self):
        builder = DifferentiationBuilder()
        result = await builder.build(
            competitive_data={
                "positioning_gaps": [
                    {"dimension": "Innovation", "opportunity_score": 9},
                ],
                "swot_summary": {
                    "weaknesses": ["Slow innovation", "High churn"],
                },
            },
            audience_needs={
                "table_stakes": [
                    {"name": "Reliability", "severity": 9},
                    {"name": "Security", "severity": 8},
                ],
                "differentiators": [
                    {"name": "Speed", "severity": 6},
                ],
            },
            positioning={},
        )
        assert len(result["pops"]) == 2
        assert len(result["pods"]) == 1
        assert len(result["competitive_vulnerabilities"]) == 2

    async def test_build_with_empty_data(self):
        builder = DifferentiationBuilder()
        result = await builder.build(
            competitive_data={},
            audience_needs={},
            positioning={},
        )
        assert result["pops"] == []
        assert result["pods"] == []
        assert result["overall_differentiation_score"] == 0.0

    async def test_pops_from_table_stakes(self):
        builder = DifferentiationBuilder()
        result = await builder.build(
            competitive_data={},
            audience_needs={
                "table_stakes": [
                    {"name": "Data Protection", "severity": 10},
                ],
            },
            positioning={},
        )
        assert len(result["pops"]) == 1
        assert result["pops"][0]["attribute"] == "Data Protection"
        assert result["pops"][0]["importance"] == "high"
