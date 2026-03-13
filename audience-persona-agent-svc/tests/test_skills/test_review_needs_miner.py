"""Tests for SKL-APA-05: Review & Needs Miner."""

from unittest.mock import AsyncMock

from app.skills.review_needs_miner import ReviewNeedsMiner
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


class TestReviewNeedsMiner:
    async def test_meta(self):
        skill = ReviewNeedsMiner(AsyncMock())
        assert skill.meta.skill_id == "SKL-APA-05"

    async def test_execute_success(self):
        tavily = AsyncMock()
        tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "G2 Reviews",
                    "url": "https://g2.com/reviews",
                    "content": "Customers need better integrations. "
                    "The product is expensive compared to alternatives. "
                    "Looking for easier onboarding.",
                }
            ]
        )
        skill = ReviewNeedsMiner(tavily)
        result = await skill.execute({"prompt": "CRM software"}, _ctx())
        assert result.success is True
        assert "needs" in result.data
        assert "objections" in result.data

    async def test_execute_with_cia_context(self):
        tavily = AsyncMock()
        tavily.search = AsyncMock(return_value=[])
        skill = ReviewNeedsMiner(tavily)
        result = await skill.execute(
            {
                "prompt": "CRM",
                "cia_context": {
                    "competitors": [{"name": "Salesforce"}, {"name": "HubSpot"}]
                },
            },
            _ctx(),
        )
        assert result.success is True
        assert tavily.search.call_count >= 3

    async def test_execute_empty_prompt(self):
        skill = ReviewNeedsMiner(AsyncMock())
        result = await skill.execute({"prompt": ""}, _ctx())
        assert result.success is False
