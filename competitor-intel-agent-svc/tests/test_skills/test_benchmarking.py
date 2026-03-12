"""Tests for SKL-CIA-10: Competitive Benchmarking Synthesizer."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.competitive_benchmarking_synthesizer import (
    CompetitiveBenchmarkingSynthesizer,
)
from app.skills.models import SkillContext


def _context():
    return SkillContext(session_id="s1", tenant_id="t1", user_role="EDITOR")


class TestBenchmarkingSynthesizer:
    async def test_meta_skill_id(self):
        skill = CompetitiveBenchmarkingSynthesizer()
        assert skill.meta.skill_id == "SKL-CIA-10"

    async def test_no_client_returns_stub(self):
        skill = CompetitiveBenchmarkingSynthesizer(anthropic_client=None)
        result = await skill.execute(
            {"raw_data": "data", "prompt": "benchmark"}, _context()
        )
        assert result.success
        assert "LLM not available" in result.data.get("summary", "")

    async def test_no_data_returns_empty(self):
        skill = CompetitiveBenchmarkingSynthesizer()
        result = await skill.execute({"raw_data": "", "prompt": "test"}, _context())
        assert result.success

    async def test_with_anthropic_client(self):
        report = {
            "report": {
                "executive_summary": "The competitive landscape shows...",
                "competitor_matrix": {
                    "dimensions": ["product", "pricing", "support"],
                    "scores": {"Acme": {"product": 8, "pricing": 6, "support": 7}},
                },
                "key_findings": [
                    "Acme leads in product features",
                    "Price gap exists for SMBs",
                ],
                "strategic_recommendations": [
                    {
                        "recommendation": "Launch SMB tier",
                        "impact": "high",
                        "effort": "medium",
                    }
                ],
                "confidence_score": 0.85,
            }
        }
        import json

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(report))]
        mock_message.usage = MagicMock(input_tokens=800, output_tokens=600)

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        skill = CompetitiveBenchmarkingSynthesizer(anthropic_client=mock_client)
        result = await skill.execute(
            {"raw_data": "full competitor data...", "prompt": "benchmark competitors"},
            _context(),
        )
        assert result.success
        assert "report_data" in result.data
        assert result.tokens_used == 1400

    async def test_handles_llm_error(self):
        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("Rate limited"))

        skill = CompetitiveBenchmarkingSynthesizer(anthropic_client=mock_client)
        result = await skill.execute(
            {"raw_data": "data", "prompt": "test"}, _context()
        )
        assert not result.success
        assert "Rate limited" in result.error

    async def test_viewer_not_in_allowed_roles(self):
        skill = CompetitiveBenchmarkingSynthesizer()
        assert "VIEWER" not in skill.meta.allowed_roles
