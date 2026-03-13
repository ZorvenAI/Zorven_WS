"""Tests for SKL-APA-02: Forum & Community Miner."""

from unittest.mock import AsyncMock

from app.skills.forum_community_miner import ForumCommunityMiner
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


class TestForumCommunityMiner:
    async def test_meta(self):
        skill = ForumCommunityMiner(AsyncMock(), AsyncMock())
        assert skill.meta.skill_id == "SKL-APA-02"

    async def test_execute_success(self):
        tavily = AsyncMock()
        tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "Reddit: SaaS pain points",
                    "url": "https://reddit.com/r/saas/123",
                    "content": "I need a better solution. The frustration with "
                    "current tools is the steep learning curve.",
                }
            ]
        )
        skill = ForumCommunityMiner(tavily, AsyncMock())
        result = await skill.execute({"prompt": "SaaS tools"}, _ctx())
        assert result.success is True
        assert "context" in result.data
        assert "community_insights" in result.data
        assert "language_patterns" in result.data

    async def test_execute_empty_prompt(self):
        skill = ForumCommunityMiner(AsyncMock(), AsyncMock())
        result = await skill.execute({"prompt": ""}, _ctx())
        assert result.success is False
