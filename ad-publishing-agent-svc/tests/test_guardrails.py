"""Tests for the three-layer guardrail system."""

import pytest

from app.logic.guardrails import InputGuardrails, OutputGuardrails, PlanGuardrails


class TestInputGuardrails:
    def setup_method(self):
        self.guard = InputGuardrails()

    def test_valid_context_passes(self):
        context = {
            "creative_packages": [{"ad_units": [{"image_url": "gs://x"}]}],
            "blueprint": {
                "campaign_name": "Test",
                "funnel_stages": [{"stage": "TOFU"}],
                "total_budget_usd": 100,
                "duration_days": 30,
            },
            "meta_credentials": {
                "access_token": "tok",
                "ad_account_id": "123",
            },
            "company": {},
        }
        errors = self.guard.check(context)
        assert errors == []

    def test_missing_creative_packages(self):
        context = {
            "creative_packages": [],
            "blueprint": {"campaign_name": "X", "funnel_stages": [{}]},
            "meta_credentials": {"access_token": "t", "ad_account_id": "1"},
        }
        errors = self.guard.check(context)
        assert any("IG-08" in e for e in errors)

    def test_missing_blueprint(self):
        context = {
            "creative_packages": [{"ad_units": [{"image_url": "x"}]}],
            "blueprint": {},
            "meta_credentials": {"access_token": "t", "ad_account_id": "1"},
        }
        errors = self.guard.check(context)
        assert any("IG-09" in e for e in errors)

    def test_missing_credentials(self):
        context = {
            "creative_packages": [{"ad_units": [{"image_url": "x"}]}],
            "blueprint": {"campaign_name": "X", "funnel_stages": [{}]},
            "meta_credentials": {},
            "sandbox_mode": False,
        }
        errors = self.guard.check(context)
        assert any("IG-10" in e for e in errors)

    def test_sandbox_mode_skips_credential_check(self):
        context = {
            "creative_packages": [{"ad_units": [{"image_url": "x"}]}],
            "blueprint": {
                "campaign_name": "X",
                "funnel_stages": [{}],
                "total_budget_usd": 100,
                "duration_days": 30,
            },
            "meta_credentials": {},
            "sandbox_mode": True,
        }
        errors = self.guard.check(context)
        assert not any("IG-10" in e for e in errors)

    def test_spend_cap_exceeded(self):
        context = {
            "creative_packages": [{"ad_units": [{"image_url": "x"}]}],
            "blueprint": {
                "campaign_name": "X",
                "funnel_stages": [{}],
                "total_budget_usd": 60000,
                "duration_days": 30,
            },
            "meta_credentials": {"access_token": "t", "ad_account_id": "1"},
        }
        errors = self.guard.check(context, daily_spend_cap_usd=500.0)
        assert any("IG-11" in e for e in errors)

    def test_gcs_url_accepted_as_image(self):
        """CGA uses gcs_url instead of image_url — should pass validation."""
        context = {
            "creative_packages": [{"ad_units": [{"gcs_url": "gs://bucket/img.jpg"}]}],
            "blueprint": {
                "campaign_name": "X",
                "funnel_stages": [{}],
                "total_budget_usd": 100,
                "duration_days": 30,
            },
            "company": {},
        }
        errors = self.guard.check(context)
        assert not any("IG-08" in e and "image" in e for e in errors)

    def test_housing_industry_missing_category(self):
        context = {
            "creative_packages": [{"ad_units": [{"image_url": "x"}]}],
            "blueprint": {
                "campaign_name": "X",
                "funnel_stages": [{}],
                "total_budget_usd": 100,
                "duration_days": 30,
                "special_ad_categories": [],
            },
            "meta_credentials": {"access_token": "t", "ad_account_id": "1"},
            "company": {"industry": "Real Estate"},
        }
        errors = self.guard.check(context)
        assert any("IG-12" in e for e in errors)


class TestPlanGuardrails:
    def setup_method(self):
        self.guard = PlanGuardrails()

    def test_always_requires_approval(self):
        context = {"blueprint": {}, "sandbox_mode": True}
        result = self.guard.check(context)
        assert result["requires_approval"] is True

    def test_sandbox_mode_not_production(self):
        context = {"blueprint": {}, "sandbox_mode": True}
        result = self.guard.check(context)
        assert result["is_production"] is False

    def test_production_mode(self):
        context = {"blueprint": {}, "sandbox_mode": False}
        result = self.guard.check(context)
        assert result["is_production"] is True

    def test_budget_exceeds_max(self):
        context = {
            "blueprint": {"total_budget_usd": 50000, "funnel_stages": []},
            "sandbox_mode": True,
        }
        result = self.guard.check(context, max_campaign_budget_usd=10000)
        assert any("PG-03" in e for e in result["errors"])


class TestOutputGuardrails:
    def setup_method(self):
        self.guard = OutputGuardrails()

    def test_valid_published_entities(self):
        entities = {
            "campaign_id": "c1",
            "ad_set_ids": ["as1"],
            "ad_ids": ["a1"],
            "creative_ids": ["cr1"],
            "campaign_status": "ACTIVE",
        }
        result = self.guard.check(entities)
        assert result["all_valid"] is True

    def test_missing_campaign_id(self):
        entities = {"ad_set_ids": ["as1"], "ad_ids": ["a1"]}
        result = self.guard.check(entities)
        assert result["all_valid"] is False
        assert any("OG-01" in e for e in result["errors"])

    def test_missing_ads(self):
        entities = {"campaign_id": "c1", "ad_set_ids": ["as1"], "ad_ids": []}
        result = self.guard.check(entities)
        assert result["all_valid"] is False
