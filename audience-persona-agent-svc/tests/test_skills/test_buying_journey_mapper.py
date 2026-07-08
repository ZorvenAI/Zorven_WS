"""Tests for SKL-APA-10: Buying Journey Mapper."""

import json
from unittest.mock import AsyncMock, MagicMock

from app.skills.buying_journey_mapper import BuyingJourneyMapper
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


def _mock_anthropic():
    data = {
        "journey_maps": [
            {
                "persona_slug": "enterprise-it-leader",
                "persona_label": "Enterprise IT Leader",
                "total_estimated_cycle_days": 90,
                "stages": [
                    {
                        "name": "Awareness",
                        "touchpoints": ["Blog", "LinkedIn"],
                        "emotional_state": "curious",
                        "estimated_days": 14,
                    },
                    {
                        "name": "Consideration",
                        "touchpoints": ["Webinar", "Case study"],
                        "emotional_state": "interested",
                        "estimated_days": 21,
                    },
                ],
            }
        ],
        "total_estimated_cycle_days": 90,
    }
    mock_client = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(data), type="text")]
    mock_message.usage = MagicMock(input_tokens=200, output_tokens=300)
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    return mock_client


class TestBuyingJourneyMapper:
    async def test_meta(self):
        skill = BuyingJourneyMapper()
        assert skill.meta.skill_id == "SKL-APA-10"

    async def test_execute_success(self):
        client = _mock_anthropic()
        skill = BuyingJourneyMapper(client)
        result = await skill.execute(
            {
                "prompt": "SaaS personas",
                "research_results": {
                    "SKL-APA-09": {
                        "personas": [
                            {
                                "slug": "enterprise-it-leader",
                                "segment_label": "Enterprise IT Leader",
                            }
                        ]
                    }
                },
            },
            _ctx(),
        )
        assert result.success is True
        assert "journey_maps" in result.data
        assert len(result.data["journey_maps"]) == 1
        assert result.data["journey_maps"][0]["stages"][0]["name"] == "Awareness"

    async def test_no_personas(self):
        skill = BuyingJourneyMapper(_mock_anthropic())
        result = await skill.execute(
            {
                "prompt": "test",
                "research_results": {"SKL-APA-09": {"personas": []}},
            },
            _ctx(),
        )
        assert result.success is True
        assert result.data["journey_maps"] == []

    async def test_no_client_stub(self):
        skill = BuyingJourneyMapper(anthropic_client=None)
        result = await skill.execute(
            {
                "prompt": "test",
                "research_results": {
                    "SKL-APA-09": {
                        "personas": [{"slug": "test", "segment_label": "Test"}]
                    }
                },
            },
            _ctx(),
        )
        assert result.success is True
        assert result.data["journey_maps"] == []
