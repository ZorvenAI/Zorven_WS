"""Tests for SKL-MRA-02: IndustryDataExtraction."""

from unittest.mock import AsyncMock

import pytest

from app.services.api_clients import TavilySearchClient
from app.skills.industry_data_extraction import IndustryDataExtraction
from app.skills.models import SkillContext


def _make_skill(results=None) -> IndustryDataExtraction:
    tavily = TavilySearchClient("")
    tavily.search = AsyncMock(return_value=results or [])
    return IndustryDataExtraction(tavily)


def _ctx() -> SkillContext:
    return SkillContext(session_id="s1", tenant_id="t1")


class TestIndustryDataExtraction:
    async def test_success(self):
        skill = _make_skill(
            [
                {
                    "title": "Report",
                    "url": "https://a.com",
                    "content": "Data",
                    "score": 0.9,
                }
            ]
        )
        result = await skill.execute({"queries": ["AI industry data"]}, _ctx())
        assert result.success
        assert result.data["extraction_count"] == 1
        assert len(result.data["sources"]) == 1

    async def test_empty_queries_fails(self):
        skill = _make_skill()
        result = await skill.execute({"queries": []}, _ctx())
        assert not result.success
        assert "No queries" in result.error

    async def test_deduplicates(self):
        skill = _make_skill(
            [
                {"title": "A", "url": "https://a.com", "content": "X"},
                {"title": "B", "url": "https://a.com", "content": "Y"},
            ]
        )
        result = await skill.execute({"queries": ["test"]}, _ctx())
        assert result.data["extraction_count"] == 1

    async def test_meta_correct(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-MRA-02"
