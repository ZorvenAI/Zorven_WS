"""Tests for CGA API schemas."""

import pytest

from app.api.schemas import (
    CGAResponse,
    ExecuteRequest,
    GeneratedImage,
    HookVariant,
    TenantContext,
)


class TestExecuteRequest:
    """Test ExecuteRequest schema."""

    def test_execute_request_defaults(self):
        req = ExecuteRequest(input_prompt="Generate ad creatives")
        assert req.input_prompt == "Generate ad creatives"
        assert req.input_context == {}
        assert req.tenant_context == {}
        assert req.config == {}
        assert req.previous_outputs == {}

    def test_execute_request_with_all_fields(self):
        req = ExecuteRequest(
            input_prompt="Create ad creatives for EV campaign",
            input_context={"company_name": "ChargePoint", "sector": "EV"},
            tenant_context={"tenant_id": "t1", "company_name": "ChargePoint"},
            config={"temperature": 0.7},
            previous_outputs={
                "campaign_architecture": {
                    "campaign_blueprint": {"campaign_name": "Test"},
                    "confidence_score": 0.85,
                }
            },
        )
        assert req.input_context["company_name"] == "ChargePoint"
        assert req.previous_outputs["campaign_architecture"]["confidence_score"] == 0.85


class TestTenantContext:
    """Test TenantContext schema."""

    def test_tenant_context_defaults(self):
        tc = TenantContext()
        assert tc.tenant_id == ""
        assert tc.company_name == ""
        assert tc.user_role == "VIEWER"
        assert tc.gcs_raw_bucket == ""
        assert tc.gcs_processed_bucket == ""
        assert tc.rag_data_store_id == ""


class TestCGAResponse:
    """Test CGAResponse schema."""

    def test_cga_response_defaults(self):
        resp = CGAResponse()
        assert resp.query == ""
        assert resp.creative_package == {}
        assert resp.ad_set_packages == []
        assert resp.generated_images == []
        assert resp.hooks == []
        assert resp.copy_variants == []
        assert resp.ctas == []
        assert resp.compliance_results == []
        assert resp.total_images_generated == 0
        assert resp.confidence_score == 0.0
        assert resp.image_gen_cost_usd == 0.0
        assert resp.caa_context_used is False
        assert resp.image_gen_failed is False
        assert resp.gcs_uri == ""
        assert resp.execution_time_ms == 0


class TestGeneratedImage:
    """Test GeneratedImage sub-model."""

    def test_generated_image_model(self):
        img = GeneratedImage(
            ad_set_name="fleet-managers-tofu",
            variant_id="v1",
            aspect_ratio="1:1",
            gcs_url="gs://bucket/img.png",
            prompt_used="Professional fleet charging station",
            provider="nano_banana_2",
            cost_usd=0.065,
            generation_time_ms=3200,
        )
        assert img.ad_set_name == "fleet-managers-tofu"
        assert img.variant_id == "v1"
        assert img.aspect_ratio == "1:1"
        assert img.provider == "nano_banana_2"
        assert img.cost_usd == 0.065
        assert img.generation_time_ms == 3200


class TestHookVariant:
    """Test HookVariant scroll_stop_power bounds."""

    def test_hook_variant_score_bounds(self):
        """scroll_stop_power must be between 0 and 100."""
        hook = HookVariant(
            ad_set_name="test-tofu",
            hook_text="Did you know your fleet is losing $10k/month?",
            funnel_stage="tofu",
            hook_type="pain_point",
            scroll_stop_power=85.5,
            char_count=48,
        )
        assert hook.scroll_stop_power == 85.5

        with pytest.raises(Exception):
            HookVariant(scroll_stop_power=-1)

        with pytest.raises(Exception):
            HookVariant(scroll_stop_power=101)
