"""Tests for StrategySynthesizer (SKL-BPA-10)."""

import pytest

from app.logic.strategy_synthesizer import StrategySynthesizer


class TestStrategySynthesizer:
    """Test strategy synthesis logic."""

    async def test_synthesize_full_strategy(self):
        synth = StrategySynthesizer()
        result = await synth.synthesize(
            recommended={
                "statement": "For fleet managers who need reliable charging",
                "framework_used": "classic",
                "scores": {
                    "clarity": 85,
                    "differentiation": 72,
                    "believability": 80,
                    "memorability": 78,
                    "overall": 79,
                },
            },
            alternatives=[],
            canvas={"fit_score": 85},
            maps=[{"map_id": "pm-1"}],
            differentiation={
                "pods": [{"attribute": "Speed"}],
                "overall_differentiation_score": 72,
            },
            context={"mra": {"data": True}, "cia": {"data": True}},
        )
        assert result["executive_summary"]
        assert "classic" in result["executive_summary"]
        assert result["implementation_guidelines"]
        assert len(result["implementation_guidelines"]) == 5
        assert result["wf1_data_summary"]["mra_available"] is True
        assert result["wf1_data_summary"]["cia_available"] is True

    async def test_synthesize_empty_strategy(self):
        synth = StrategySynthesizer()
        result = await synth.synthesize(
            recommended={},
            alternatives=[],
            canvas={},
            maps=[],
            differentiation={},
            context={},
        )
        assert "pending" in result["executive_summary"].lower()

    async def test_risk_assessment_low_differentiation(self):
        synth = StrategySynthesizer()
        result = await synth.synthesize(
            recommended={
                "statement": "Test",
                "framework_used": "classic",
                "scores": {"differentiation": 45, "believability": 80},
            },
            alternatives=[],
            canvas={},
            maps=[],
            differentiation={"overall_differentiation_score": 45},
            context={},
        )
        risks = result["risk_assessment"]
        assert any(r["risk"] == "Low differentiation score" for r in risks)

    async def test_risk_assessment_low_believability(self):
        synth = StrategySynthesizer()
        result = await synth.synthesize(
            recommended={
                "statement": "Test",
                "framework_used": "classic",
                "scores": {"differentiation": 80, "believability": 45},
            },
            alternatives=[],
            canvas={},
            maps=[],
            differentiation={},
            context={},
        )
        risks = result["risk_assessment"]
        assert any(r["risk"] == "Low believability score" for r in risks)
