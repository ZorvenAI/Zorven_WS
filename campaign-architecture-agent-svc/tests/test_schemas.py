"""Tests for CAA Pydantic request/response schemas."""

import pytest

from app.api.schemas import (
    CAAResponse,
    CampaignBlueprint,
    ExecuteRequest,
    FunnelStage,
    TargetingSpec,
)


class TestExecuteRequest:
    """Test ExecuteRequest model."""

    def test_execute_request_valid(self):
        """Valid payload parses correctly."""
        req = ExecuteRequest(
            input_prompt="Design a Meta campaign",
            input_context={"company_name": "Acme"},
            config={"daily_budget": 500},
        )
        assert req.input_prompt == "Design a Meta campaign"
        assert req.config["daily_budget"] == 500
        assert req.previous_outputs == {}

    def test_execute_request_missing_prompt(self):
        """Empty payload still parses (all fields have defaults)."""
        req = ExecuteRequest()
        assert req.input_prompt == ""
        assert req.input_context == {}


class TestCAAResponse:
    """Test CAAResponse model."""

    def test_caa_response_structure(self):
        """CAAResponse has all expected keys with defaults."""
        resp = CAAResponse()
        assert resp.query == ""
        assert resp.blueprint == {}
        assert resp.funnel_map == {}
        assert resp.targeting_specs == []
        assert resp.placement_budget == {}
        assert resp.test_plan == {}
        assert resp.kpi_targets == {}
        assert resp.performance_projections == {}
        assert resp.risk_assessment == {}
        assert resp.creative_briefs == []
        assert resp.special_ad_category == ""
        assert resp.meta_api_compatible is False
        assert resp.confidence_score == 0.0
        assert resp.findings == []
        assert resp.recommendations == []
        assert resp.sources == []
        assert resp.wf1_context_used is False
        assert resp.gcs_uri == ""
        assert resp.execution_time_ms == 0


class TestFunnelStage:
    """Test FunnelStage model."""

    def test_funnel_stage_validation(self):
        """FunnelStage accepts valid stage values."""
        stage = FunnelStage(
            stage="tofu",
            meta_objective="AWARENESS",
            budget_pct=30.0,
            description="Top of funnel awareness",
        )
        assert stage.stage == "tofu"
        assert stage.meta_objective == "AWARENESS"
        assert stage.budget_pct == 30.0


class TestCampaignBlueprint:
    """Test CampaignBlueprint model."""

    def test_campaign_blueprint_structure(self):
        """CampaignBlueprint has correct defaults."""
        bp = CampaignBlueprint()
        assert bp.campaign_name == ""
        assert bp.campaign_objective == ""
        assert bp.special_ad_category == ""
        assert bp.buying_type == "AUCTION"
        assert bp.daily_budget == 0.0
        assert bp.cbo_enabled is False
        assert bp.ad_sets == []
