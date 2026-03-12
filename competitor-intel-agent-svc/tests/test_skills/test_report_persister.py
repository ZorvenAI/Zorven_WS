"""Tests for SKL-CIA-11: Competitor Report Persister."""

from app.skills.competitor_report_persister import CompetitorReportPersister
from app.skills.models import SkillContext


def _context():
    return SkillContext(session_id="s1", tenant_id="t1", user_role="EDITOR")


class TestReportPersister:
    async def test_meta_skill_id(self):
        skill = CompetitorReportPersister()
        assert skill.meta.skill_id == "SKL-CIA-11"

    async def test_not_idempotent(self):
        skill = CompetitorReportPersister()
        assert skill.meta.idempotent is False

    async def test_no_data_returns_not_persisted(self):
        skill = CompetitorReportPersister()
        result = await skill.execute({"report_data": {}}, _context())
        assert result.success
        assert result.data["persisted"] is False

    async def test_disabled_gcs_and_rag(self):
        skill = CompetitorReportPersister(gcs_enabled=False, rag_enabled=False)
        result = await skill.execute(
            {"report_data": {"key": "value"}, "prompt": "test"},
            _context(),
        )
        assert result.success
        assert result.data["persisted"] is False
        assert len(result.data["persisted_to"]) == 0

    async def test_gcs_enabled_persists(self):
        skill = CompetitorReportPersister(gcs_enabled=True, rag_enabled=False)
        result = await skill.execute(
            {"report_data": {"key": "value"}, "prompt": "test"},
            _context(),
        )
        assert result.success
        assert "gcs" in result.data["persisted_to"]

    async def test_editor_in_allowed_roles(self):
        skill = CompetitorReportPersister()
        assert "EDITOR" in skill.meta.allowed_roles
        assert "VIEWER" not in skill.meta.allowed_roles
