"""Tests for SKL-APA-09: Persona Synthesizer."""

import json
from unittest.mock import AsyncMock, MagicMock

from app.skills.persona_synthesizer import PersonaSynthesizer
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


def _mock_anthropic(personas=None):
    data = {
        "personas": personas
        or [
            {
                "slug": "enterprise-it-leader",
                "segment_label": "Enterprise IT Leader",
                "priority_score": 0.9,
                "data_source": "research_based",
                "pain_points": ["Integration complexity"],
                "motivations": ["ROI improvement"],
                "confidence_score": 0.8,
            }
        ],
        "segment_matrix": {"tech_savvy": {"enterprise-it-leader": 0.9}},
        "differentiation_notes": "Clear differentiation by role.",
    }
    mock_client = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(data), type="text")]
    mock_message.usage = MagicMock(input_tokens=200, output_tokens=400)
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    return mock_client


class TestPersonaSynthesizer:
    async def test_meta(self):
        skill = PersonaSynthesizer()
        assert skill.meta.skill_id == "SKL-APA-09"
        assert skill.meta.timeout_ms == 90000

    async def test_execute_success(self):
        client = _mock_anthropic()
        skill = PersonaSynthesizer(client)
        result = await skill.execute(
            {
                "prompt": "SaaS buyer personas",
                "research_results": {
                    "SKL-APA-07": {"demographic_profiles": [{"segment_label": "IT"}]},
                    "SKL-APA-08": {"psychographic_profiles": []},
                },
            },
            _ctx(),
        )
        assert result.success is True
        assert "personas" in result.data
        assert len(result.data["personas"]) == 1
        assert result.data["personas"][0]["data_source"] == "research_based"

    async def test_crm_grounded_data_source(self):
        client = _mock_anthropic()
        skill = PersonaSynthesizer(client)
        result = await skill.execute(
            {
                "prompt": "test",
                "research_results": {
                    "SKL-APA-05c": {
                        "has_sufficient_data": True,
                        "segments": [{"name": "Tech"}],
                    },
                    "SKL-APA-07": {"demographic_profiles": []},
                },
            },
            _ctx(),
        )
        assert result.success is True
        for p in result.data["personas"]:
            assert p["data_source"] in ("crm_grounded", "research_based")

    async def test_no_client_stub(self):
        skill = PersonaSynthesizer(anthropic_client=None)
        result = await skill.execute(
            {"prompt": "test", "research_results": {"SKL-APA-07": {}}},
            _ctx(),
        )
        assert result.success is True
        assert result.data["personas"] == []

    async def test_max_personas_cap(self):
        many_personas = [
            {"slug": f"p-{i}", "segment_label": f"Persona {i}"} for i in range(10)
        ]
        client = _mock_anthropic(personas=many_personas)
        skill = PersonaSynthesizer(client)
        result = await skill.execute(
            {
                "prompt": "test",
                "research_results": {"SKL-APA-07": {"demographic_profiles": []}},
            },
            _ctx(),
        )
        assert result.success is True
        # Default MAX_PERSONAS=5, MAX_PERSONAS_LIMIT=8
        assert len(result.data["personas"]) <= 8
