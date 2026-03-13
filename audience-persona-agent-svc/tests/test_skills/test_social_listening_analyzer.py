"""Tests for SKL-APA-03: Social Listening Analyzer."""

from unittest.mock import AsyncMock

from app.skills.social_listening_analyzer import SocialListeningAnalyzer
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


class TestSocialListeningAnalyzer:
    async def test_meta(self):
        skill = SocialListeningAnalyzer(AsyncMock())
        assert skill.meta.skill_id == "SKL-APA-03"

    async def test_execute_success(self):
        tavily = AsyncMock()
        tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "LinkedIn engagement",
                    "url": "https://example.com/social",
                    "content": "LinkedIn users prefer long-form content. "
                    "TikTok drives brand awareness for Gen Z.",
                }
            ]
        )
        skill = SocialListeningAnalyzer(tavily)
        result = await skill.execute({"prompt": "B2B SaaS"}, _ctx())
        assert result.success is True
        assert "platform_behaviors" in result.data
        platforms = [b["platform"] for b in result.data["platform_behaviors"]]
        assert "LinkedIn" in platforms

    async def test_execute_empty_prompt(self):
        skill = SocialListeningAnalyzer(AsyncMock())
        result = await skill.execute({"prompt": ""}, _ctx())
        assert result.success is False
