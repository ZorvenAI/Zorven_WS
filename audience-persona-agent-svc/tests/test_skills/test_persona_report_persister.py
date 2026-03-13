"""Tests for SKL-APA-11: Persona Report Persister."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.skills.persona_report_persister import PersonaReportPersister
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="ADMIN")


class TestPersonaReportPersister:
    async def test_meta(self):
        skill = PersonaReportPersister()
        assert skill.meta.skill_id == "SKL-APA-11"
        assert "VIEWER" not in skill.meta.allowed_roles

    async def test_no_report_data(self):
        skill = PersonaReportPersister()
        result = await skill.execute({"prompt": "test", "report_data": {}}, _ctx())
        assert result.success is True
        assert result.data["persisted"] is False

    async def test_registry_update(self):
        mock_registry = AsyncMock()
        skill = PersonaReportPersister(persona_registry=mock_registry)
        report = {
            "personas": [
                {"slug": "it-leader", "segment_label": "IT Leader"},
                {"slug": "cfo", "segment_label": "CFO"},
            ]
        }
        result = await skill.execute({"prompt": "test", "report_data": report}, _ctx())
        assert result.success is True
        assert result.data["registry_updated"] is True
        assert "registry" in result.data["persisted_to"]
        assert mock_registry.upsert_persona.call_count == 2

    async def test_gcs_enabled(self):
        skill = PersonaReportPersister(gcs_enabled=True)
        report = {"personas": [{"slug": "test"}]}
        result = await skill.execute({"prompt": "test", "report_data": report}, _ctx())
        assert result.success is True
        assert result.data["gcs_enabled"] is True
        assert "gcs" in result.data["persisted_to"]

    async def test_rag_enabled(self):
        skill = PersonaReportPersister(rag_enabled=True)
        report = {"personas": [{"slug": "test"}]}
        with patch("app.skills.persona_report_persister.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock(status_code=200)
            mock_resp.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            result = await skill.execute(
                {"prompt": "test", "report_data": report}, _ctx()
            )
            assert result.success is True
            assert "rag" in result.data["persisted_to"]

    async def test_registry_failure_graceful(self):
        mock_registry = AsyncMock()
        mock_registry.upsert_persona.side_effect = Exception("Redis down")
        skill = PersonaReportPersister(persona_registry=mock_registry)
        report = {"personas": [{"slug": "test", "segment_label": "Test"}]}
        result = await skill.execute({"prompt": "test", "report_data": report}, _ctx())
        assert result.success is True
        assert result.data["registry_updated"] is False
