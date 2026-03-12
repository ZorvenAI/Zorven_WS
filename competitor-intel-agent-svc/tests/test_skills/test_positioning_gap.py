"""Tests for SKL-CIA-09: Positioning Gap Analyzer."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.positioning_gap_analyzer import PositioningGapAnalyzer
from app.skills.models import SkillContext


def _context():
    return SkillContext(session_id="s1", tenant_id="t1", user_role="EDITOR")


class TestPositioningGapAnalyzer:
    async def test_meta_skill_id(self):
        skill = PositioningGapAnalyzer()
        assert skill.meta.skill_id == "SKL-CIA-09"

    async def test_no_client_returns_stub(self):
        skill = PositioningGapAnalyzer(anthropic_client=None)
        result = await skill.execute(
            {"raw_data": "data", "prompt": "analyze"}, _context()
        )
        assert result.success
        assert "LLM not available" in result.data.get("message", "")

    async def test_no_data_returns_empty(self):
        skill = PositioningGapAnalyzer()
        result = await skill.execute({"raw_data": "", "prompt": "test"}, _context())
        assert result.success
        assert result.data["positioning_gaps"] == []

    async def test_with_anthropic_client(self):
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(
                text='{"positioning_map": {"x_axis": "Price", "y_axis": "Features", "positions": [{"competitor": "Acme", "x": 0.7, "y": 0.8}]}, "positioning_gaps": [{"dimension": "SMB pricing", "gap_description": "No affordable tier for small businesses", "opportunity_score": 8, "evidence": ["Pricing data shows..."], "gap_type": "price"}], "differentiation_dimensions": [{"dimension": "AI features", "leader": "Acme", "laggard": "Beta", "gap_size": "large"}]}'
            )
        ]
        mock_message.usage = MagicMock(input_tokens=600, output_tokens=400)

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        skill = PositioningGapAnalyzer(anthropic_client=mock_client)
        result = await skill.execute(
            {"raw_data": "competitor data...", "prompt": "find gaps"},
            _context(),
        )
        assert result.success
        assert len(result.data["positioning_gaps"]) == 1
        assert result.data["positioning_gaps"][0]["opportunity_score"] == 8
        assert "x_axis" in result.data["positioning_map"]
        assert result.tokens_used == 1000

    async def test_handles_llm_error(self):
        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("Timeout"))

        skill = PositioningGapAnalyzer(anthropic_client=mock_client)
        result = await skill.execute(
            {"raw_data": "data", "prompt": "test"}, _context()
        )
        assert not result.success
        assert "Timeout" in result.error
