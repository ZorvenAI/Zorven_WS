"""Tests for optimization app views."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from optimization.models import (
    CampaignRegistry,
    OptimizationAction,
    OptimizationRecommendation,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def viewer_client(api_client, user, public_tenant):
    """Client with tenant membership (OWNER role, acts as viewer+)."""
    from tenants.models import Membership

    api_client.force_authenticate(user=user)
    Membership.objects.get_or_create(
        user=user,
        tenant=public_tenant,
        defaults={"role": Membership.Role.OWNER},
    )
    api_client.credentials(HTTP_X_TENANT_ID=str(public_tenant.id))
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user, public_tenant):
    """Client with admin/superuser + tenant membership."""
    from tenants.models import Membership

    api_client.force_authenticate(user=admin_user)
    Membership.objects.get_or_create(
        user=admin_user,
        tenant=public_tenant,
        defaults={"role": Membership.Role.OWNER},
    )
    api_client.credentials(HTTP_X_TENANT_ID=str(public_tenant.id))
    return api_client


@pytest.fixture
def campaign(public_tenant):
    return CampaignRegistry.objects.create(
        tenant=public_tenant,
        meta_campaign_id="view_test_campaign",
        meta_ad_account_id="act_111222",
        campaign_name="View Test Campaign",
        objective="CONVERSIONS",
        daily_budget_usd=100.00,
        target_cpa_usd=15.00,
        target_roas=2.0,
        start_date=timezone.now() - timedelta(days=3),
    )


@pytest.fixture
def pending_recommendation(public_tenant, campaign):
    return OptimizationRecommendation.objects.create(
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


class TestCampaignRegistryViewSet:
    def test_list_campaigns(self, viewer_client, campaign):
        response = viewer_client.get("/api/v1/optimization/campaigns/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_retrieve_campaign(self, viewer_client, campaign):
        response = viewer_client.get(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["campaign_name"] == "View Test Campaign"

    def test_update_settings(self, admin_client, campaign):
        response = admin_client.patch(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/settings/",
            {"optimization_mode": "autonomous"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.optimization_mode == "autonomous"

    def test_update_guardrail_config(self, admin_client, campaign):
        response = admin_client.patch(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/settings/",
            {"guardrail_config": {"max_daily_budget_increase_pct": 30}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        campaign.refresh_from_db()
        assert campaign.guardrail_config["max_daily_budget_increase_pct"] == 30


class TestRecommendationActions:
    def test_list_recommendations(
        self, viewer_client, campaign, pending_recommendation
    ):
        response = viewer_client.get(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/recommendations/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["action_type"] == "PAUSE"

    def test_approve_recommendation(
        self, admin_client, campaign, pending_recommendation
    ):
        rec_id = str(pending_recommendation.recommendation_id)
        response = admin_client.post(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/recommendations/{rec_id}/approve/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "approved"

    def test_approve_with_modified_values(
        self, admin_client, campaign, pending_recommendation
    ):
        rec_id = str(pending_recommendation.recommendation_id)
        response = admin_client.post(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/recommendations/{rec_id}/approve/",
            {"modified_values": {"daily_budget": 40}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "modified"

    def test_reject_recommendation(
        self, admin_client, campaign, pending_recommendation
    ):
        rec_id = str(pending_recommendation.recommendation_id)
        response = admin_client.post(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/recommendations/{rec_id}/reject/",
            {"reason": "Want to wait longer"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "rejected"

    def test_approve_expired_recommendation(
        self, admin_client, campaign, public_tenant
    ):
        expired_rec = OptimizationRecommendation.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            action_type="SCALE",
            entity_type="ad_set",
            entity_id="expired_123",
            rationale="Old recommendation",
            priority="LOW",
            tick_id="tick_old",
            data_freshness=timezone.now() - timedelta(hours=50),
            expires_at=timezone.now() - timedelta(hours=1),
        )
        rec_id = str(expired_rec.recommendation_id)
        response = admin_client.post(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/recommendations/{rec_id}/approve/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_410_GONE

    def test_approve_nonexistent_recommendation(self, admin_client, campaign):
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = admin_client.post(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/recommendations/{fake_id}/approve/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_batch_approve(self, admin_client, campaign, public_tenant):
        # Create multiple pending recommendations
        for i in range(3):
            OptimizationRecommendation.objects.create(
                tenant=public_tenant,
                campaign=campaign,
                action_type="PAUSE",
                entity_type="ad_set",
                entity_id=f"batch_{i}",
                rationale=f"Reason {i}",
                priority="MEDIUM",
                tick_id="tick_batch",
                data_freshness=timezone.now(),
                expires_at=timezone.now() + timedelta(hours=48),
            )

        response = admin_client.post(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/recommendations/approve-all/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["approved_count"] >= 3


class TestActionsAuditLog:
    def test_list_actions(self, viewer_client, campaign, public_tenant):
        OptimizationAction.objects.create(
            tenant=public_tenant,
            campaign=campaign,
            action_type="PAUSE",
            entity_type="ad_set",
            entity_id="action_123",
            old_value={"status": "ACTIVE"},
            new_value={"status": "PAUSED"},
            mode="autonomous",
            rationale="CPA 2.3x target",
        )
        response = viewer_client.get(
            f"/api/v1/optimization/campaigns/{campaign.campaign_id}/actions/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["action_type"] == "PAUSE"


class TestTickCallback:
    @override_settings(ORCHESTRATOR_CALLBACK_TOKEN="test-callback-token")
    def test_callback_valid_token(self, api_client, campaign):
        response = api_client.post(
            "/api/v1/optimization/callback/tick-result/",
            {
                "tick_id": "tick_cb_001",
                "tenant_id": str(campaign.tenant_id) if campaign.tenant else "",
                "campaign_id": str(campaign.campaign_id),
                "mode": "manual",
                "campaigns_processed": 1,
                "recommendations_generated": 1,
                "recommendations": [
                    {
                        "action_type": "PAUSE",
                        "entity_type": "ad_set",
                        "entity_id": "cb_adset_1",
                        "rationale": "CPA too high",
                        "priority": "HIGH",
                    }
                ],
                "actions": [],
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN="test-callback-token",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["recommendations_created"] == 1

    @override_settings(ORCHESTRATOR_CALLBACK_TOKEN="correct-token")
    def test_callback_invalid_token(self, api_client, campaign):
        response = api_client.post(
            "/api/v1/optimization/callback/tick-result/",
            {
                "tick_id": "tick_invalid",
                "tenant_id": "",
                "campaign_id": str(campaign.campaign_id),
                "mode": "manual",
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN="wrong-token",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @override_settings(ORCHESTRATOR_CALLBACK_TOKEN="test-token")
    def test_callback_campaign_not_found(self, api_client):
        response = api_client.post(
            "/api/v1/optimization/callback/tick-result/",
            {
                "tick_id": "tick_missing",
                "tenant_id": "",
                "campaign_id": "00000000-0000-0000-0000-000000000001",
                "mode": "manual",
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN="test-token",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @override_settings(ORCHESTRATOR_CALLBACK_TOKEN="test-token")
    def test_callback_persists_performance_kpis(self, api_client, campaign):
        assert campaign.actual_cpa_usd is None
        assert campaign.last_metrics_update is None

        response = api_client.post(
            "/api/v1/optimization/callback/tick-result/",
            {
                "tick_id": "tick_perf_001",
                "tenant_id": str(campaign.tenant_id) if campaign.tenant else "",
                "campaign_id": str(campaign.campaign_id),
                "mode": "manual",
                "performance": {
                    "avg_cpa": 12.34,
                    "avg_roas": 3.5,
                    "avg_ctr": 2.75,
                    "spend_today": 42.0,
                },
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN="test-token",
        )
        assert response.status_code == status.HTTP_200_OK

        campaign.refresh_from_db()
        assert float(campaign.actual_cpa_usd) == 12.34
        assert float(campaign.actual_roas) == 3.5
        assert float(campaign.actual_ctr) == 2.75
        assert float(campaign.actual_spend_today_usd) == 42.0
        assert campaign.last_metrics_update is not None

    @override_settings(ORCHESTRATOR_CALLBACK_TOKEN="test-token")
    def test_callback_missing_perf_preserves_existing_kpis(self, api_client, campaign):
        from decimal import Decimal

        from django.utils import timezone

        earlier = timezone.now()
        campaign.actual_cpa_usd = Decimal("9.99")
        campaign.actual_roas = Decimal("4.20")
        campaign.actual_ctr = Decimal("1.50")
        campaign.actual_spend_today_usd = Decimal("25.00")
        campaign.last_metrics_update = earlier
        campaign.save()

        response = api_client.post(
            "/api/v1/optimization/callback/tick-result/",
            {
                "tick_id": "tick_perf_002",
                "tenant_id": str(campaign.tenant_id) if campaign.tenant else "",
                "campaign_id": str(campaign.campaign_id),
                "mode": "manual",
                # No performance key at all
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN="test-token",
        )
        assert response.status_code == status.HTTP_200_OK

        campaign.refresh_from_db()
        assert campaign.actual_cpa_usd == Decimal("9.99")
        assert campaign.actual_roas == Decimal("4.20")
        assert campaign.actual_ctr == Decimal("1.50")
        assert campaign.actual_spend_today_usd == Decimal("25.00")
        assert campaign.last_metrics_update == earlier

    @override_settings(ORCHESTRATOR_CALLBACK_TOKEN="test-token")
    def test_callback_partial_perf_only_updates_provided(self, api_client, campaign):
        from decimal import Decimal

        campaign.actual_cpa_usd = Decimal("9.99")
        campaign.actual_roas = Decimal("4.20")
        campaign.save()

        response = api_client.post(
            "/api/v1/optimization/callback/tick-result/",
            {
                "tick_id": "tick_perf_003",
                "tenant_id": str(campaign.tenant_id) if campaign.tenant else "",
                "campaign_id": str(campaign.campaign_id),
                "mode": "manual",
                # Only ctr provided; cpa/roas must not be nulled out.
                "performance": {"avg_ctr": 3.14, "avg_cpa": None},
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN="test-token",
        )
        assert response.status_code == status.HTTP_200_OK

        campaign.refresh_from_db()
        assert campaign.actual_cpa_usd == Decimal("9.99")
        assert campaign.actual_roas == Decimal("4.20")
        assert float(campaign.actual_ctr) == 3.14
        assert campaign.last_metrics_update is not None
