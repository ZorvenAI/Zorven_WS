"""Basic model tests for intelligence_loop."""

from datetime import timedelta

import pytest
from django.utils import timezone

from intelligence_loop.models import (
    CampaignIntelligence,
    LearningDocument,
    LearningRecord,
    WF2RerunRequest,
)
from optimization.models import CampaignRegistry

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(public_tenant):
    return CampaignRegistry.objects.create(
        tenant=public_tenant,
        meta_campaign_id="ila_test_1",
        meta_ad_account_id="act_ila",
        campaign_name="ILA Test",
        objective="CONVERSIONS",
        daily_budget_usd=50.00,
        start_date=timezone.now() - timedelta(days=2),
    )


def test_create_intelligence_with_learning_and_doc(public_tenant, campaign):
    intel = CampaignIntelligence.objects.create(
        tenant=public_tenant,
        campaign=campaign,
        job_id="job-1",
        mode="store_only",
        trigger_source="manual",
        intelligence_report={"summary": "ok"},
    )
    learning = LearningRecord.objects.create(
        tenant=public_tenant,
        intelligence=intel,
        category="audience",
        headline="Lookalike 1% beats interest stack",
        confidence=82,
        impact="HIGH",
        target_workflow="WF1",
        target_agent="APA",
    )
    doc = LearningDocument.objects.create(
        tenant=public_tenant,
        learning=learning,
        content="Lookalike audiences outperformed by 38%.",
    )
    assert intel.learnings.count() == 1
    assert doc.learning == learning
    assert str(intel.intelligence_id)


def test_wf2_rerun_request(public_tenant, campaign):
    intel = CampaignIntelligence.objects.create(
        tenant=public_tenant,
        campaign=campaign,
        job_id="job-2",
        trigger_source="manual",
    )
    learning = LearningRecord.objects.create(
        tenant=public_tenant,
        intelligence=intel,
        category="messaging",
        headline="Reframe positioning",
        confidence=70,
        impact="MEDIUM",
        target_workflow="WF2",
        target_agent="BPA",
    )
    req = WF2RerunRequest.objects.create(
        tenant=public_tenant,
        learning=learning,
        requested_agent="BPA",
        rationale="Positioning needs refresh based on creative fatigue learnings.",
        expires_at=timezone.now() + timedelta(hours=72),
    )
    assert req.status == "pending"
