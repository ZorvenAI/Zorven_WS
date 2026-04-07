"""Tests for intelligence_loop Celery tasks."""

from datetime import timedelta

import pytest
from django.utils import timezone

from intelligence_loop.models import (
    CampaignIntelligence,
    LearningRecord,
    WF2RerunRequest,
)
from intelligence_loop.tasks import expire_pending_wf2_requests
from optimization.models import CampaignRegistry

pytestmark = pytest.mark.django_db


@pytest.fixture
def learning(public_tenant):
    campaign = CampaignRegistry.objects.create(
        tenant=public_tenant,
        meta_campaign_id="exp_test",
        meta_ad_account_id="act_exp",
        campaign_name="Expiry Test",
        objective="CONVERSIONS",
        daily_budget_usd=10.00,
        start_date=timezone.now() - timedelta(days=1),
    )
    intel = CampaignIntelligence.objects.create(
        tenant=public_tenant,
        campaign=campaign,
        job_id="job-exp",
        trigger_source="manual",
    )
    return LearningRecord.objects.create(
        tenant=public_tenant,
        intelligence=intel,
        category="messaging",
        headline="Test",
        confidence=80,
        impact="HIGH",
        target_workflow="WF2",
        target_agent="BPA",
    )


def test_expire_pending_wf2_flips_old_pendings(public_tenant, learning):
    now = timezone.now()
    expired = WF2RerunRequest.objects.create(
        tenant=public_tenant,
        learning=learning,
        requested_agent="BPA",
        rationale="r",
        expires_at=now - timedelta(hours=1),
    )
    fresh = WF2RerunRequest.objects.create(
        tenant=public_tenant,
        learning=learning,
        requested_agent="BPA",
        rationale="r",
        expires_at=now + timedelta(hours=24),
    )

    count = expire_pending_wf2_requests()
    assert count == 1

    expired.refresh_from_db()
    fresh.refresh_from_db()
    assert expired.status == "expired"
    assert fresh.status == "pending"
