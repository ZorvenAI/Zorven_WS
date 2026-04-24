"""
Seed sample OptimizationRecommendation records for sandbox/demo campaigns.

All seeded recommendations include [SANDBOX] in the rationale so demo users
understand the data is illustrative, not from real Meta Insights.

Usage:
    python manage.py seed_sandbox_recommendations
    python manage.py seed_sandbox_recommendations --dry-run
    python manage.py seed_sandbox_recommendations --clear   # remove seeded recs
"""

import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from optimization.models import CampaignRegistry, OptimizationRecommendation

SANDBOX_TICK_PREFIX = "sandbox-seed-"

RECOMMENDATION_TEMPLATES = [
    {
        "action_type": "PAUSE",
        "entity_type": "ad_set",
        "priority": "HIGH",
        "rationale": (
            "[SANDBOX DEMO] This ad set has a CPA of $18.42, which is "
            "2.1x above the campaign target of $8.75. CTR has declined "
            "32% over the past 3 days, suggesting audience fatigue. "
            "Recommend pausing to stop budget waste."
        ),
        "current_values": {
            "cpa_usd": 18.42,
            "ctr_pct": 0.68,
            "daily_spend_usd": 24.50,
            "impressions_3d": 3620,
        },
        "proposed_values": {
            "status": "PAUSED",
            "daily_spend_usd": 0,
        },
        "projected_impact": {
            "daily_savings_usd": 24.50,
            "projected_cpa_reduction_pct": 15,
        },
    },
    {
        "action_type": "SCALE",
        "entity_type": "ad_set",
        "priority": "MEDIUM",
        "rationale": (
            "[SANDBOX DEMO] This ad set is performing well with a CPA "
            "of $3.12 (64% below target) and a ROAS of 4.8x. "
            "Increasing budget by 20% could capture additional "
            "conversions while staying within guardrails."
        ),
        "current_values": {
            "cpa_usd": 3.12,
            "roas": 4.8,
            "daily_budget_usd": 25.00,
            "conversions_7d": 56,
        },
        "proposed_values": {
            "daily_budget_usd": 30.00,
            "budget_increase_pct": 20,
        },
        "projected_impact": {
            "additional_conversions_weekly": 11,
            "projected_roas": 4.5,
        },
    },
    {
        "action_type": "REALLOCATE",
        "entity_type": "campaign",
        "priority": "MEDIUM",
        "rationale": (
            "[SANDBOX DEMO] Budget is unevenly distributed across ad "
            "sets. TOFU set is spending 45% of budget but delivering "
            "only 18% of conversions. Recommend shifting $10/day from "
            "TOFU to the high-performing BOFU set."
        ),
        "current_values": {
            "tofu_spend_pct": 45,
            "tofu_conversion_pct": 18,
            "bofu_spend_pct": 20,
            "bofu_conversion_pct": 52,
        },
        "proposed_values": {
            "tofu_daily_budget_usd": 15.00,
            "bofu_daily_budget_usd": 35.00,
        },
        "projected_impact": {
            "projected_cpa_reduction_pct": 22,
            "projected_conversion_increase_pct": 15,
        },
    },
    {
        "action_type": "REFRESH",
        "entity_type": "ad",
        "priority": "LOW",
        "rationale": (
            "[SANDBOX DEMO] Ad creative has been running for 12 days. "
            "Frequency is 3.8 (above the 3.0 threshold) and CTR has "
            "dropped 28% from its peak. Recommend refreshing the "
            "creative to combat audience fatigue."
        ),
        "current_values": {
            "frequency": 3.8,
            "ctr_pct": 1.02,
            "ctr_peak_pct": 1.42,
            "days_running": 12,
        },
        "proposed_values": {
            "action": "generate_new_creative",
            "keep_targeting": True,
        },
        "projected_impact": {
            "projected_ctr_recovery_pct": 20,
            "estimated_frequency_reset": 1.0,
        },
    },
    {
        "action_type": "ADJUST_BID",
        "entity_type": "ad_set",
        "priority": "CRITICAL",
        "rationale": (
            "[SANDBOX DEMO] CPA has spiked to $25.60 in the last 24h "
            "(3x target). The competitive landscape shows increased "
            "auction pressure. Recommend lowering bid cap by 15% and "
            "monitoring for 24h before further action."
        ),
        "current_values": {
            "cpa_usd": 25.60,
            "bid_cap_usd": 12.00,
            "auction_overlap_pct": 67,
            "cost_per_click_usd": 2.85,
        },
        "proposed_values": {
            "bid_cap_usd": 10.20,
            "bid_reduction_pct": 15,
        },
        "projected_impact": {
            "projected_cpa_usd": 18.50,
            "projected_savings_daily_usd": 8.40,
        },
    },
]


class Command(BaseCommand):
    help = "Seed sandbox recommendation records for demo purposes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without writing to the database.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Remove all previously seeded sandbox recommendations.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if options["clear"]:
            qs = OptimizationRecommendation.objects.filter(
                tick_id__startswith=SANDBOX_TICK_PREFIX
            )
            count = qs.count()
            if not dry_run:
                qs.delete()
            prefix = "[DRY RUN] " if dry_run else ""
            self.stdout.write(
                self.style.SUCCESS(f"{prefix}Removed {count} sandbox recommendations.")
            )
            return

        campaigns = list(CampaignRegistry.objects.all()[:5])
        if not campaigns:
            self.stdout.write(
                self.style.WARNING("No campaigns found. Nothing to seed.")
            )
            return

        now = timezone.now()
        created = 0

        for i, template in enumerate(RECOMMENDATION_TEMPLATES):
            campaign = campaigns[i % len(campaigns)]
            tick_id = f"{SANDBOX_TICK_PREFIX}{uuid.uuid4().hex[:8]}"

            # Use a real-looking entity ID from the campaign
            if template["entity_type"] == "campaign":
                entity_id = campaign.meta_campaign_id or str(campaign.campaign_id)
            elif template["entity_type"] == "ad_set":
                ad_sets = campaign.ad_sets or []
                entity_id = (
                    ad_sets[0].get("id", f"stub_adset_{i}")
                    if ad_sets
                    else f"stub_adset_{i}"
                )
            else:
                ads = campaign.ads or []
                entity_id = ads[0].get("id", f"stub_ad_{i}") if ads else f"stub_ad_{i}"

            if dry_run:
                self.stdout.write(
                    f"  [DRY RUN] Would create {template['priority']} "
                    f"{template['action_type']} recommendation for "
                    f"{campaign.campaign_name}"
                )
            else:
                OptimizationRecommendation.objects.create(
                    tenant=campaign.tenant,
                    campaign=campaign,
                    recommendation_id=uuid.uuid4(),
                    action_type=template["action_type"],
                    entity_type=template["entity_type"],
                    entity_id=entity_id,
                    current_values=template["current_values"],
                    proposed_values=template["proposed_values"],
                    rationale=template["rationale"],
                    projected_impact=template["projected_impact"],
                    priority=template["priority"],
                    status="pending",
                    expires_at=now + timedelta(hours=48),
                    tick_id=tick_id,
                    data_freshness=now - timedelta(minutes=15),
                    guardrails_applied=["GR-01", "GR-03", "GR-07"],
                )
            created += 1

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Seeded {created} sandbox recommendations "
                f"across {len(campaigns)} campaigns."
            )
        )
