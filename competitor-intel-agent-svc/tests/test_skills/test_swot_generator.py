"""Tests for SKL-CIA-08: SWOT Analysis Generator."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.swot_analysis_generator import SWOTAnalysisGenerator
from app.skills.models import SkillContext


def _context():
    return SkillContext(session_id="s1", tenant_id="t1", user_role="EDITOR")


class TestSWOTGenerator:
    async def test_meta_skill_id(self):
        skill = SWOTAnalysisGenerator()
        assert skill.meta.skill_id == "SKL-CIA-08"

    async def test_no_client_returns_stub(self):
        skill = SWOTAnalysisGenerator(anthropic_client=None)
        result = await skill.execute(
            {"raw_data": "competitor data here", "prompt": "analyze"},
            _context(),
        )
        assert result.success
        assert "LLM not available" in result.data.get("message", "")

    async def test_no_data_returns_empty(self):
        skill = SWOTAnalysisGenerator()
        result = await skill.execute({"raw_data": "", "prompt": "test"}, _context())
        assert result.success
        assert result.data["swot_analyses"] == []

    async def test_with_anthropic_client(self):
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(
                text='{"swot_analyses": [{"competitor": "Acme", "slug": "acme", "strengths": ["Strong brand"], "weaknesses": ["High price"], "opportunities": ["AI growth"], "threats": ["New entrants"], "confidence_score": 0.8, "citations": ["https://acme.com"]}]}',
                type="text",
            )
        ]
        mock_message.usage = MagicMock(input_tokens=500, output_tokens=300)

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        skill = SWOTAnalysisGenerator(anthropic_client=mock_client)
        result = await skill.execute(
            {"raw_data": "Acme Corp data...", "prompt": "analyze competitors"},
            _context(),
        )
        assert result.success
        analyses = result.data["swot_analyses"]
        assert len(analyses) == 1
        assert analyses[0]["competitor"] == "Acme"
        assert len(analyses[0]["strengths"]) > 0
        assert result.tokens_used == 800

    async def test_handles_llm_error(self):
        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

        skill = SWOTAnalysisGenerator(anthropic_client=mock_client)
        result = await skill.execute(
            {"raw_data": "data", "prompt": "test"}, _context()
        )
        assert not result.success
        assert "API error" in result.error

    async def test_viewer_not_in_allowed_roles(self):
        skill = SWOTAnalysisGenerator()
        assert "VIEWER" not in skill.meta.allowed_roles
