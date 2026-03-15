"""Tests for SKL-VoCA-02: Odoo Survey Response Extractor."""

import pytest
from unittest.mock import AsyncMock

from app.skills.odoo_survey_extractor import OdooSurveyExtractor
from app.skills.models import SkillContext


@pytest.fixture
def extractor(mock_odoo_client, mock_redis_manager):
    """OdooSurveyExtractor with mocked dependencies."""
    return OdooSurveyExtractor(
        odoo_client=mock_odoo_client,
        redis_manager=mock_redis_manager,
    )


@pytest.mark.unit
def test_meta_attributes(extractor):
    """Skill meta has correct ID and name."""
    assert extractor.meta.skill_id == "SKL-VoCA-02"
    assert extractor.meta.name == "odoo_survey_extractor"
    assert "VIEWER" not in extractor.meta.allowed_roles


@pytest.mark.asyncio
@pytest.mark.unit
async def test_nps_detection(extractor, mock_odoo_client, mock_redis_manager):
    """NPS questions are auto-detected from numerical_box with 0-10 range."""
    ctx = SkillContext(
        session_id="s1",
        tenant_id="test-tenant",
        user_role="EDITOR",
        operating_mode="full",
    )
    mock_redis_manager.get_odoo_cache = AsyncMock(return_value=None)

    # Survey data
    mock_odoo_client.search_read = AsyncMock()
    call_count = 0

    async def search_read_side_effect(model, domain, fields, limit=100, **kwargs):
        nonlocal call_count
        call_count += 1
        if model == "survey.survey":
            return [{"id": 1, "title": "CSAT Survey", "description": ""}]
        elif model == "survey.question":
            return [
                {
                    "id": 10,
                    "title": "How likely are you to recommend us?",
                    "question_type": "numerical_box",
                    "constr_min_value": 0,
                    "constr_max_value": 10,
                    "survey_id": [1, "CSAT Survey"],
                },
                {
                    "id": 11,
                    "title": "Additional comments",
                    "question_type": "text_box",
                    "constr_min_value": None,
                    "constr_max_value": None,
                    "survey_id": [1, "CSAT Survey"],
                },
            ]
        elif model == "survey.user_input":
            return [
                {
                    "id": 100,
                    "survey_id": [1, "CSAT Survey"],
                    "partner_id": [50, "Respondent A"],
                    "create_date": "2025-11-15 10:00:00",
                    "scoring_total": 9.0,
                }
            ]
        elif model == "survey.user_input_line":
            return [
                {
                    "id": 1001,
                    "user_input_id": [100, ""],
                    "question_id": [10, "NPS Question"],
                    "value_text": "",
                    "value_number": 9.0,
                    "value_suggested_row": None,
                },
                {
                    "id": 1002,
                    "user_input_id": [100, ""],
                    "question_id": [11, "Comments"],
                    "value_text": "Great service!",
                    "value_number": None,
                    "value_suggested_row": None,
                },
            ]
        return []

    mock_odoo_client.search_read = AsyncMock(
        side_effect=search_read_side_effect
    )

    result = await extractor.execute({"prompt": "nps analysis"}, ctx)
    assert result.success is True
    assert result.data["nps_questions_detected"] == 1
    assert result.data["nps_detection_confidence"] > 0
    # The profile should have nps_responses
    profile = result.data["profile"]
    assert len(profile["nps_responses"]) == 1
    assert profile["nps_responses"][0]["is_nps_response"] is True
    assert profile["nps_responses"][0]["score"] == 9.0
