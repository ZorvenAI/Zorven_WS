"""Tests for SKL-MRA-03: MarketAnalysisSynthesis."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.skills.market_analysis_synthesis import MarketAnalysisSynthesis
from app.skills.models import SkillContext


def _ctx() -> SkillContext:
    return SkillContext(session_id="s1", tenant_id="t1")


class TestMarketAnalysisSynthesis:
    async def test_stub_mode_without_client(self):
        skill = MarketAnalysisSynthesis(anthropic_client=None)
        result = await skill.execute(
            {"raw_data": "Some data", "prompt": "AI market"}, _ctx()
        )
        assert result.success
        assert "Stub" in result.data["analysis"]
        assert result.data["confidence_score"] == 0.3

    async def test_no_raw_data_fails(self):
        skill = MarketAnalysisSynthesis(anthropic_client=None)
        result = await skill.execute({"raw_data": "", "prompt": "test"}, _ctx())
        assert not result.success
        assert "No raw data" in result.error

    async def test_with_anthropic_client(self):
        mock_client = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.content = [
            MagicMock(
                text='{"analysis": "Test", "findings": ["f1"], "recommendations": ["r1"], "confidence_score": 0.8, "citations": []}'
            )
        ]
        mock_msg.usage = MagicMock(input_tokens=100, output_tokens=200)
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        skill = MarketAnalysisSynthesis(anthropic_client=mock_client)
        result = await skill.execute(
            {"raw_data": "Data here", "prompt": "test", "analysis_type": "sizing"},
            _ctx(),
        )
        assert result.success
        assert result.tokens_used == 300

    async def test_meta_correct(self):
        skill = MarketAnalysisSynthesis()
        assert skill.meta.skill_id == "SKL-MRA-03"
        assert "VIEWER" not in skill.meta.allowed_roles
