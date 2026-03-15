"""Tests for SKL-VoCA-13: VoC Report Persister."""

import pytest

from app.skills.voc_report_persister import VoCReportPersister
from app.skills.models import SkillContext


@pytest.fixture
def persister_no_gcs():
    """VoCReportPersister with GCS disabled."""
    return VoCReportPersister(
        gcs_enabled=False,
        rag_enabled=False,
        rag_service_url="",
        feedback_registry=None,
        alert_producer=None,
    )


@pytest.mark.unit
def test_meta_attributes(persister_no_gcs):
    """Skill meta has correct ID and name."""
    assert persister_no_gcs.meta.skill_id == "SKL-VoCA-13"
    assert persister_no_gcs.meta.name == "voc_report_persister"
    assert persister_no_gcs.meta.idempotent is False
    assert "VIEWER" not in persister_no_gcs.meta.allowed_roles


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_no_gcs(persister_no_gcs, basic_skill_context):
    """When GCS is disabled, returns success with empty report_url."""
    result = await persister_no_gcs.execute(
        {
            "report_data": {"summary": "test report"},
            "prompt": "Persist VoC report",
            "themes": [],
            "sentiment": {},
            "nps_data": {},
            "coverage_data": {},
        },
        basic_skill_context,
    )
    assert result.success is True
    assert result.data["report_url"] == ""
    assert result.data["indexed_count"] == 0
    assert result.data["registry_updated"] is False
