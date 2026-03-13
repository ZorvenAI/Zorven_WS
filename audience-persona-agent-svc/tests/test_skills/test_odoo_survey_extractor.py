"""Tests for SKL-APA-05b: Odoo Survey Data Extractor."""

from unittest.mock import AsyncMock

from app.skills.odoo_survey_data_extractor import OdooSurveyDataExtractor
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


def _mock_odoo():
    client = AsyncMock()
    client.search_read = AsyncMock(
        side_effect=[
            # surveys
            [{"id": 1, "title": "Customer Survey", "description": ""}],
            # responses
            [
                {
                    "id": 10,
                    "survey_id": [1, "Customer Survey"],
                    "create_date": "2025-01-01",
                    "scoring_total": 80,
                },
                {
                    "id": 11,
                    "survey_id": [1, "Customer Survey"],
                    "create_date": "2025-01-02",
                    "scoring_total": 90,
                },
            ],
            # lines
            [
                {
                    "user_input_id": 10,
                    "question_id": 1,
                    "value_text": "Great product",
                    "value_number": 0,
                    "value_suggested_row": False,
                },
            ],
        ]
    )
    return client


def _mock_redis(cached=None):
    rm = AsyncMock()
    rm.get_odoo_survey_cache = AsyncMock(return_value=cached)
    rm.set_odoo_survey_cache = AsyncMock()
    return rm


class TestOdooSurveyDataExtractor:
    async def test_meta(self):
        skill = OdooSurveyDataExtractor(AsyncMock(), AsyncMock())
        assert skill.meta.skill_id == "SKL-APA-05b"
        assert "VIEWER" not in skill.meta.allowed_roles

    async def test_execute_success(self):
        odoo = _mock_odoo()
        redis = _mock_redis()
        skill = OdooSurveyDataExtractor(odoo, redis)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is True
        assert "survey_data" in result.data
        assert result.data["survey_data"]["total_responses"] == 2
        redis.set_odoo_survey_cache.assert_called_once()

    async def test_cache_hit(self):
        cached = {
            "context": "cached data",
            "sources": [],
            "survey_data": {"total_responses": 5},
        }
        redis = _mock_redis(cached=cached)
        skill = OdooSurveyDataExtractor(AsyncMock(), redis)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is True
        assert result.data == cached

    async def test_no_surveys(self):
        odoo = AsyncMock()
        odoo.search_read = AsyncMock(return_value=[])
        redis = _mock_redis()
        skill = OdooSurveyDataExtractor(odoo, redis)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is True
        assert result.data["survey_data"] == {}

    async def test_odoo_error(self):
        odoo = AsyncMock()
        odoo.search_read = AsyncMock(side_effect=Exception("Connection error"))
        redis = _mock_redis()
        skill = OdooSurveyDataExtractor(odoo, redis)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.success is False
