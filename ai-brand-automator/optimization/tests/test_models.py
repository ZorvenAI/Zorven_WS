"""Tests for optimization app models."""

from datetime import timedelta

import pytest
from django.utils import timezone

from optimization.models import (
    CampaignRegistry,
    OptimizationAction,
    OptimizationRecommendation,
)

pytestmark = pytest.mark.django_db


class TestCampaignRegistry:
    def test_create_campaign(self, public_tenant):
        campaign = CampaignRegistry.objects.create(
            tenant=public_tenant,
            meta_campaign_id="123456789",
            meta_ad_account_id="act_111222333",
            campaign_name="Test Campaign",
            objective="CONVERSIONS",
            status="active",
            daily_budget_usd=100.00,
            start_date=timezone.now() - timedelta(days=3),
        )
        assert campaign.campaign_id is not None
        assert campaign.optimization_mode == "manual"
        assert campaign.sandbox_mode is True
        assert str(campaign) == "Test Campaign (123456789)"

    def test_age_days(self, public_tenant):
        campaign = CampaignRegistry.objects.create(
            tenant=public_tenant,
            meta_campaign_id="age_test",
            meta_ad_account_id="act_111",
            campaign_name="Age Test",
            objective="REACH",
            daily_budget_usd=50.00,
            start_date=timezone.now() - timedelta(days=5),
        )
        assert campaign.age_days == 5

    def test_unique_tenant_meta_campaign(self, public_tenant):
        CampaignRegistry.objects.create(
            tenant=public_tenant,
            meta_campaign_id="unique_test",
            meta_ad_account_id="act_111",
            campaign_name="First",
            objective="CONVERSIONS",
            daily_budget_usd=100.00,
            start_date=timezone.now(),
        )
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            CampaignRegistry.objects.create(
                tenant=public_tenant,
                meta_campaign_id="unique_test",
                meta_ad_account_id="act_111",
                campaign_name="Duplicate",
                objective="CONVERSIONS",
                daily_budget_usd=100.00,
                start_date=timezone.now(),
            )

    def test_ad_sets_and_ads_json(self, public_tenant):
        campaign = CampaignRegistry.objects.create(
            tenant=public_tenant,
            meta_campaign_id="json_test",
            meta_ad_account_id="act_111",
            campaign_name="JSON Test",
            objective="CONVERSIONS",
            daily_budget_usd=100.00,
            start_date=timezone.now(),
            ad_sets=[
                {"id": "as1", "name": "TOFU", "status": "ACTIVE", "daily_budget": 50}
            ],
            ads=[{"id": "ad1", "ad_set_id": "as1", "name": "Ad 1", "status": "ACTIVE"}],
        )
        assert len(campaign.ad_sets) == 1
        assert campaign.ad_sets[0]["id"] == "as1"
        assert len(campaign.ads) == 1


class TestOptimizationRecommendation:
    @pytest.fixture
    def campaign(self, public_tenant):
        return CampaignRegistry.objects.create(
            tenant=public_tenant,
            meta_campaign_id="rec_test_campaign",
            meta_ad_account_id="act_111",
            campaign_name="Rec Test Campaign",
            objective="CONVERSIONS",
            daily_budget_usd=100.00,
            start_date=timezone.now() - timedelta(days=3),
        )

    def test_create_recommendation(self, public_tenant, campaign):
        rec = OptimizationRecommendation.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            action_type="PAUSE",
            entity_type="ad_set",
            entity_id="123456",
            current_values={"status": "ACTIVE", "daily_budget": 50},
            proposed_values={"status": "PAUSED"},
            rationale="CPA $31 exceeds 2x target ($15)",
            projected_impact={"estimated_savings_usd": 25},
            priority="HIGH",
            tick_id="tick_001",
            data_freshness=timezone.now() - timedelta(hours=3),
            expires_at=timezone.now() + timedelta(hours=48),
        )
        assert rec.status == "pending"
        assert rec.recommendation_id is not None
        assert "PAUSE" in str(rec)

    def test_is_expired(self, public_tenant, campaign):
        rec = OptimizationRecommendation.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            action_type="SCALE",
            entity_type="ad_set",
            entity_id="789",
            rationale="ROAS exceeds target",
            priority="MEDIUM",
            tick_id="tick_002",
            data_freshness=timezone.now(),
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert rec.is_expired is True

    def test_not_expired(self, public_tenant, campaign):
        rec = OptimizationRecommendation.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            action_type="SCALE",
            entity_type="ad_set",
            entity_id="789",
            rationale="ROAS exceeds target",
            priority="MEDIUM",
            tick_id="tick_003",
            data_freshness=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=47),
        )
        assert rec.is_expired is False

    def test_approved_not_expired(self, public_tenant, campaign):
        rec = OptimizationRecommendation.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            action_type="PAUSE",
            entity_type="ad_set",
            entity_id="456",
            rationale="Test",
            priority="LOW",
            status="approved",
            tick_id="tick_004",
            data_freshness=timezone.now(),
            expires_at=timezone.now() - timedelta(hours=1),
        )
        # is_expired only applies to pending status
        assert rec.is_expired is False


class TestOptimizationAction:
    @pytest.fixture
    def campaign(self, public_tenant):
        return CampaignRegistry.objects.create(
            tenant=public_tenant,
            meta_campaign_id="action_test_campaign",
            meta_ad_account_id="act_111",
            campaign_name="Action Test Campaign",
            objective="CONVERSIONS",
            daily_budget_usd=100.00,
            start_date=timezone.now() - timedelta(days=5),
        )

    def test_create_action(self, public_tenant, campaign):
        action = OptimizationAction.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            action_type="PAUSE",
            entity_type="ad_set",
            entity_id="123456",
            old_value={"status": "ACTIVE"},
            new_value={"status": "PAUSED"},
            mode="autonomous",
            rationale="CPA 2.3x target",
            meta_api_response={"success": True},
            verified=True,
        )
        assert action.action_id is not None
        assert action.verified is True
        assert "PAUSE" in str(action)

    def test_action_with_recommendation(self, public_tenant, campaign):
        rec = OptimizationRecommendation.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            action_type="SCALE",
            entity_type="ad_set",
            entity_id="789",
            rationale="ROAS high",
            priority="HIGH",
            tick_id="tick_005",
            data_freshness=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )
        action = OptimizationAction.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            recommendation=rec,
            action_type="SCALE",
            entity_type="ad_set",
            entity_id="789",
            old_value={"daily_budget": 50},
            new_value={"daily_budget": 60},
            mode="manual",
            rationale="Approved by user",
        )
        assert action.recommendation == rec
        assert action.mode == "manual"
