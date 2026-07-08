"""Tests for SKL-APA-08: Psychographic & Behavioral Profiler."""

import json
from unittest.mock import AsyncMock, MagicMock

from app.skills.psychographic_behavioral_profiler import (
    PsychographicBehavioralProfiler,
)
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


def _mock_anthropic():
    data = {
        "psychographic_profiles": [
            {
                "segment_label": "Enterprise IT Leader",
                "values": ["Innovation", "Efficiency"],
                "decision_style": "data-driven",
            }
        ],
        "behavioral_patterns": [
            {
                "pattern": "Reads industry reports",
                "evidence": "survey",
                "frequency": "weekly",
            }
        ],
    }
    mock_client = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(data), type="text")]
    mock_message.usage = MagicMock(input_tokens=150, output_tokens=250)
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    return mock_client


class TestPsychographicBehavioralProfiler:
    async def test_meta(self):
        skill = PsychographicBehavioralProfiler()
        assert skill.meta.skill_id == "SKL-APA-08"

    async def test_execute_success(self):
        client = _mock_anthropic()
        skill = PsychographicBehavioralProfiler(client)
        result = await skill.execute(
            {
                "prompt": "SaaS personas",
                "research_results": {
                    "SKL-APA-07": {
                        "demographic_profiles": [{"segment_label": "IT Leader"}]
                    }
                },
            },
            _ctx(),
        )
        assert result.success is True
        assert "psychographic_profiles" in result.data
        assert "behavioral_patterns" in result.data

    async def test_no_client_stub(self):
        skill = PsychographicBehavioralProfiler(anthropic_client=None)
        result = await skill.execute(
            {"prompt": "test", "research_results": {"SKL-APA-01": {}}},
            _ctx(),
        )
        assert result.success is True
        assert result.data["psychographic_profiles"] == []

    async def test_no_research_data(self):
        skill = PsychographicBehavioralProfiler(_mock_anthropic())
        result = await skill.execute({"prompt": "test", "research_results": {}}, _ctx())
        assert result.success is True
        assert result.data["psychographic_profiles"] == []
