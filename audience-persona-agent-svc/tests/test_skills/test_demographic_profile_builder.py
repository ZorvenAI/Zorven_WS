"""Tests for SKL-APA-07: Demographic Profile Builder."""

import json
from unittest.mock import AsyncMock, MagicMock

from app.skills.demographic_profile_builder import DemographicProfileBuilder
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


def _mock_anthropic(response_data=None):
    data = response_data or {
        "demographic_profiles": [
            {"segment_label": "Enterprise IT Leader", "age_range": "35-50"}
        ],
        "confidence_score": 0.8,
    }
    mock_client = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(data))]
    mock_message.usage = MagicMock(input_tokens=100, output_tokens=200)
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    return mock_client


class TestDemographicProfileBuilder:
    async def test_meta(self):
        skill = DemographicProfileBuilder()
        assert skill.meta.skill_id == "SKL-APA-07"
        assert skill.meta.circuit_breaker_dependency == "llm"
        assert "VIEWER" not in skill.meta.allowed_roles

    async def test_execute_success(self):
        client = _mock_anthropic()
        skill = DemographicProfileBuilder(client)
        result = await skill.execute(
            {
                "prompt": "SaaS personas",
                "research_results": {
                    "SKL-APA-01": {"context": "demographics data here"}
                },
            },
            _ctx(),
        )
        assert result.success is True
        assert "demographic_profiles" in result.data
        assert len(result.data["demographic_profiles"]) == 1
        assert result.tokens_used == 300

    async def test_no_client_stub(self):
        skill = DemographicProfileBuilder(anthropic_client=None)
        result = await skill.execute(
            {"prompt": "test", "research_results": {"SKL-APA-01": {}}},
            _ctx(),
        )
        assert result.success is True
        assert result.data["demographic_profiles"] == []

    async def test_no_research_data(self):
        skill = DemographicProfileBuilder(_mock_anthropic())
        result = await skill.execute({"prompt": "test", "research_results": {}}, _ctx())
        assert result.success is True
        assert result.data["demographic_profiles"] == []

    async def test_llm_failure(self):
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=Exception("API error"))
        skill = DemographicProfileBuilder(client)
        result = await skill.execute(
            {
                "prompt": "test",
                "research_results": {"SKL-APA-01": {"context": "data"}},
            },
            _ctx(),
        )
        assert result.success is False
