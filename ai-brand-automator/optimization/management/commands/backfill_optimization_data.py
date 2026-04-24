"""
Management command to backfill OptimizationAction (ACTIVATE) and
PerformanceSnapshot records for existing CampaignRegistry rows that
were registered before those records were created at registration time.

Usage:
    python manage.py backfill_optimization_data
    python manage.py backfill_optimization_data --dry-run
"""

from django.core.management.base import BaseCommand

from optimization.models import (
    CampaignRegistry,
    OptimizationAction,
    PerformanceSnapshot,
)


class Command(BaseCommand):
    help = (
        "Backfill ACTIVATE actions and baseline PerformanceSnapshots "
        "for campaigns that lack them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        campaigns = CampaignRegistry.objects.all()

        actions_created = 0
        snapshots_created = 0

        for campaign in campaigns:
            # Check if an ACTIVATE action already exists
            has_action = OptimizationAction.objects.filter(
                campaign=campaign,
                action_type="ACTIVATE",
            ).exists()

            if not has_action:
                if dry_run:
                    self.stdout.write(
                        f"  [DRY RUN] Would create ACTIVATE action "
                        f"for {campaign.campaign_name}"
                    )
                else:
                    OptimizationAction.objects.create(
                        tenant=campaign.tenant,
                        campaign=campaign,
                        action_type="ACTIVATE",
                        entity_type="campaign",
                        entity_id=campaign.meta_campaign_id
                        or str(campaign.campaign_id),
                        old_value={},
                        new_value={
                            "status": campaign.status,
                            "daily_budget_usd": float(campaign.daily_budget_usd or 0),
                            "ad_sets": len(campaign.ad_sets or []),
                            "ads": len(campaign.ads or []),
                            "sandbox_mode": campaign.sandbox_mode,
                        },
                        mode="manual",
                        rationale=(
                            f'Campaign "{campaign.campaign_name}" published '
                            f"via Ad Publishing workflow. Daily budget "
                            f"${float(campaign.daily_budget_usd or 0):.2f}, "
                            f"{len(campaign.ad_sets or [])} ad set(s), "
                            f"{len(campaign.ads or [])} ad(s)."
                        ),
                        guardrails_applied=[],
                        meta_api_response={},
                        verified=True,
                        verification_result={"source": "backfill_optimization_data"},
                    )
                actions_created += 1

            # Check if any PerformanceSnapshot exists
            has_snapshot = PerformanceSnapshot.objects.filter(
                campaign=campaign,
            ).exists()

            if not has_snapshot:
                if dry_run:
                    self.stdout.write(
                        f"  [DRY RUN] Would create baseline snapshot "
                        f"for {campaign.campaign_name}"
                    )
                else:
                    daily_budget = float(campaign.daily_budget_usd or 0)
                    cpa = campaign.actual_cpa_usd or campaign.target_cpa_usd
                    roas = campaign.actual_roas or campaign.target_roas
                    PerformanceSnapshot.objects.create(
                        tenant=campaign.tenant,
                        campaign=campaign,
                        tick_id=f"backfill-{campaign.campaign_id}",
                        cpa_usd=float(cpa) if cpa is not None else None,
                        roas=float(roas) if roas is not None else None,
                        ctr=(
                            float(campaign.actual_ctr)
                            if campaign.actual_ctr is not None
                            else None
                        ),
                        spend_usd=daily_budget if daily_budget > 0 else None,
                    )
                snapshots_created += 1

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Backfill complete: "
                f"{actions_created} actions, "
                f"{snapshots_created} snapshots "
                f"across {campaigns.count()} campaigns."
            )
        )
