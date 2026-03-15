"""Tests for VoCAAnalyzer."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.events.catalog import EventEmitter
from app.logic.guardrails import ThreeLayerGuardrails
from app.logic.voc_analyzer import VoCAAnalyzer
from app.rbac.engine import RBACEngine
from app.skills.registry import SkillRegistry
from app.skills.models import SkillMeta, SkillResult


class _StubSkill:
    """Minimal stub skill for testing."""

    def __init__(self, skill_id: str, name: str, allowed_roles=None):
        self.meta = SkillMeta(
            skill_id=skill_id,
            name=name,
            description="stub",
            allowed_roles=allowed_roles or ["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        )

    async def execute(self, input_data, context):
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"stub": True},
        )


@pytest.fixture
def external_only_registry():
    """SkillRegistry with only external skills registered (05-08, 09-12, 13)."""
    reg = SkillRegistry()
    reg.register(_StubSkill("SKL-VoCA-05", "external_review_miner"))
    reg.register(_StubSkill("SKL-VoCA-06", "social_feedback_collector"))
    reg.register(_StubSkill("SKL-VoCA-07", "forum_discussion_miner"))
    reg.register(_StubSkill("SKL-VoCA-08", "rag_context_retrieval"))
    reg.register(
        _StubSkill(
            "SKL-VoCA-09", "sentiment_analyzer",
            allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        )
    )
    reg.register(
        _StubSkill(
            "SKL-VoCA-10", "theme_cluster_builder",
            allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        )
    )
    reg.register(
        _StubSkill(
            "SKL-VoCA-11", "nps_trend_analyzer",
            allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        )
    )
    reg.register(
        _StubSkill(
            "SKL-VoCA-12", "voc_strategy_bridge",
            allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        )
    )
    reg.register(
        _StubSkill(
            "SKL-VoCA-13", "voc_report_persister",
            allowed_roles=["OWNER", "ADMIN"],
        )
    )
    return reg


@pytest.fixture
def full_registry(external_only_registry):
    """SkillRegistry with full mode (Odoo + external) skills registered."""
    reg = external_only_registry
    reg.register(
        _StubSkill(
            "SKL-VoCA-01", "odoo_helpdesk_extractor",
            allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        )
    )
    reg.register(
        _StubSkill(
            "SKL-VoCA-02", "odoo_survey_extractor",
            allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        )
    )
    reg.register(
        _StubSkill(
            "SKL-VoCA-03", "odoo_chatter_extractor",
            allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        )
    )
    reg.register(
        _StubSkill("SKL-VoCA-04", "odoo_customer_segment_linker")
    )
    return reg


@pytest.fixture
def make_analyzer():
    """Factory to create a VoCAAnalyzer with a given registry."""

    def _make(registry):
        rbac = RBACEngine()
        guardrails = ThreeLayerGuardrails(
            redis_manager=None,
            rbac_engine=rbac,
            anthropic_client=None,
        )
        event_emitter = AsyncMock(spec=EventEmitter)
        event_emitter.emit = AsyncMock()

        return VoCAAnalyzer(
            skill_registry=registry,
            guardrails=guardrails,
            circuit_breakers={},
            event_emitter=event_emitter,
            anthropic_client=None,
        )

    return _make


@pytest.mark.asyncio
@pytest.mark.unit
async def test_detect_operating_mode_external_only(
    make_analyzer, external_only_registry
):
    """When Odoo skills are not registered, operating mode is external_only."""
    analyzer = make_analyzer(external_only_registry)
    mode = await analyzer._detect_operating_mode("test-tenant")
    assert mode == "external_only"


@pytest.mark.unit
def test_plan_skills_external_only(make_analyzer, external_only_registry):
    """In external_only mode, no Odoo skills are in the plan."""
    analyzer = make_analyzer(external_only_registry)
    plan = analyzer._plan_skills("external_only", "EDITOR", {})
    # Should NOT include Odoo skills
    assert "SKL-VoCA-01" not in plan
    assert "SKL-VoCA-02" not in plan
    assert "SKL-VoCA-03" not in plan
    assert "SKL-VoCA-04" not in plan
    # Should include external and analysis skills
    assert "SKL-VoCA-05" in plan
    assert "SKL-VoCA-06" in plan
    assert "SKL-VoCA-09" in plan
    assert "SKL-VoCA-12" in plan


@pytest.mark.unit
def test_plan_skills_full_mode(make_analyzer, full_registry):
    """In full mode, Odoo skills are included in the plan."""
    analyzer = make_analyzer(full_registry)
    plan = analyzer._plan_skills("full", "EDITOR", {})
    # Should include Odoo skills
    assert "SKL-VoCA-01" in plan
    assert "SKL-VoCA-02" in plan
    assert "SKL-VoCA-03" in plan
    assert "SKL-VoCA-04" in plan
    # Should also include external and analysis
    assert "SKL-VoCA-05" in plan
    assert "SKL-VoCA-09" in plan


@pytest.mark.unit
def test_error_response_shape(make_analyzer, external_only_registry):
    """_error_response returns the expected structure."""
    analyzer = make_analyzer(external_only_registry)
    result = analyzer._error_response("test query", "Something went wrong")
    assert result["query"] == "test query"
    assert result["operating_mode"] == ""
    assert result["voc_health_score"] == 0.0
    assert result["confidence_score"] == 0.0
    assert "Something went wrong" in result["findings"]
    assert result["sources"] == []
    assert result["recommendations"] == []
