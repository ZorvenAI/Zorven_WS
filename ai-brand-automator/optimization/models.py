"""
Models for the optimization app.

CampaignRegistry — persistent record of published Meta campaigns for optimization.
OptimizationRecommendation — COA-generated recommendations for human approval.
OptimizationAction — immutable audit log of all executed optimization actions.
"""

import uuid

from django.db import models


class CampaignRegistry(models.Model):
    """
    Persistent record of published Meta Ads campaigns available for
    continuous optimization. Populated by the ad-publishing-agent (APA-3.3)
    result handler and read by the Continuous Optimization Agent (COA-3.4).
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="campaign_registries",
    )
    company = models.ForeignKey(
        "onboarding.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="campaign_registries",
    )
    campaign_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Internal campaign identifier",
    )
    meta_campaign_id = models.CharField(
        max_length=100,
        help_text="Meta Ads campaign ID",
    )
    meta_ad_account_id = models.CharField(
        max_length=100,
        help_text="Meta Ads ad account ID",
    )
    campaign_name = models.CharField(max_length=500)
    objective = models.CharField(
        max_length=100,
        help_text="Campaign objective (CONVERSIONS, REACH, etc.)",
    )

    STATUS_CHOICES = [
        ("active", "Active"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="active")

    MODE_CHOICES = [
        ("manual", "Manual"),
        ("autonomous", "Autonomous"),
    ]
    optimization_mode = models.CharField(
        max_length=20,
        choices=MODE_CHOICES,
        default="manual",
        help_text=(
            "Manual: recommendations need approval. "
            "Autonomous: auto-execute within guardrails."
        ),
    )

    # Targets from CAA blueprint
    target_cpa_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target cost per acquisition in USD",
    )
    target_roas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target return on ad spend",
    )
    daily_budget_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Daily budget in USD",
    )
    lifetime_budget_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Lifetime budget in USD",
    )

    # Actual performance metrics (populated from COA tick callbacks)
    actual_cpa_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Latest observed cost per acquisition in USD",
    )
    actual_roas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Latest observed return on ad spend",
    )
    actual_ctr = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=(
            "Latest observed click-through rate as percentage "
            "(0.0000-100.0000) to match analytics convention"
        ),
    )
    actual_spend_today_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Spend today in USD (from latest tick)",
    )
    last_metrics_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the latest performance metrics update",
    )

    # Meta entity tree (denormalized for fast access)
    ad_sets = models.JSONField(
        default=list,
        blank=True,
        help_text="[{id, name, status, targeting, daily_budget}]",
    )
    ads = models.JSONField(
        default=list,
        blank=True,
        help_text="[{id, ad_set_id, name, status, creative_id}]",
    )

    # Campaign timeline
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)

    # Guardrail overrides (per-campaign, merged with global defaults)
    guardrail_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-campaign guardrail overrides",
    )

    # Provenance
    source_job_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="AnalysisJob that published this campaign",
    )
    brand_context_id = models.CharField(max_length=255, blank=True, default="")
    sandbox_mode = models.BooleanField(default=True)

    # Meta credentials reference (not stored here — loaded from tenant config)
    meta_access_token_ref = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Reference to encrypted Meta access token in tenant config",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "meta_campaign_id"],
                name="unique_tenant_meta_campaign",
            ),
        ]

    def __str__(self):
        return f"{self.campaign_name} ({self.meta_campaign_id})"

    @property
    def age_days(self):
        """Campaign age in days from start_date."""
        from django.utils import timezone

        if not self.start_date:
            return 0
        return (timezone.now() - self.start_date).days


class PerformanceSnapshot(models.Model):
    """
    Point-in-time performance metrics captured on each COA tick.

    Provides the 7-day trend data for the optimization dashboard chart.
    One row per tick per campaign.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="performance_snapshots",
    )
    campaign = models.ForeignKey(
        CampaignRegistry,
        on_delete=models.CASCADE,
        related_name="performance_snapshots",
    )
    tick_id = models.CharField(max_length=255)
    cpa_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    roas = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ctr = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    spend_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(
                fields=["campaign", "recorded_at"],
                name="idx_perf_snap_campaign_ts",
            ),
        ]

    def __str__(self):
        return f"{self.campaign_id} @ {self.recorded_at}"


class OptimizationRecommendation(models.Model):
    """
    COA-generated optimization recommendation for human approval.

    In manual mode, all recommendations go through this model.
    In autonomous mode, only actions exceeding guardrails are downgraded
    to recommendations here.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="optimization_recommendations",
    )
    campaign = models.ForeignKey(
        CampaignRegistry,
        on_delete=models.CASCADE,
        related_name="recommendations",
    )
    recommendation_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
    )

    ACTION_TYPE_CHOICES = [
        ("PAUSE", "Pause"),
        ("SCALE", "Scale Budget"),
        ("REALLOCATE", "Reallocate Budget"),
        ("REFRESH", "Creative Refresh"),
        ("ADJUST_BID", "Adjust Bid"),
        ("ADJUST_PLACEMENT", "Adjust Placement"),
        ("ADJUST_SCHEDULE", "Adjust Schedule"),
        ("ACTIVATE", "Activate"),
    ]
    action_type = models.CharField(max_length=50, choices=ACTION_TYPE_CHOICES)

    ENTITY_TYPE_CHOICES = [
        ("campaign", "Campaign"),
        ("ad_set", "Ad Set"),
        ("ad", "Ad"),
    ]
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES)
    entity_id = models.CharField(
        max_length=100,
        help_text="Meta entity ID",
    )

    current_values = models.JSONField(default=dict, blank=True)
    proposed_values = models.JSONField(default=dict, blank=True)
    rationale = models.TextField(help_text="Analysis rationale with data points")
    projected_impact = models.JSONField(
        default=dict,
        blank=True,
        help_text="Estimated savings or ROI improvement",
    )

    PRIORITY_CHOICES = [
        ("CRITICAL", "Critical"),
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
    ]
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES)

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("modified", "Modified"),
        ("expired", "Expired"),
        ("executed", "Executed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    approved_by = models.CharField(max_length=255, blank=True, default="")
    rejection_reason = models.TextField(blank=True, default="")
    modified_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="User-modified values before approval",
    )

    expires_at = models.DateTimeField(help_text="Auto-expire after 48h")
    executed_at = models.DateTimeField(null=True, blank=True)

    # Audit context
    tick_id = models.CharField(
        max_length=255,
        help_text="Optimization tick that generated this",
    )
    data_freshness = models.DateTimeField(
        help_text="When Meta Insights data was fetched",
    )
    guardrails_applied = models.JSONField(
        default=list,
        blank=True,
        help_text="Guardrail IDs that were evaluated",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_opt_rec_tenant_status"),
            models.Index(
                fields=["campaign", "status"], name="idx_opt_rec_campaign_status"
            ),
        ]

    def __str__(self):
        return f"{self.action_type} {self.entity_type}:{self.entity_id} ({self.status})"

    @property
    def is_expired(self):
        from django.utils import timezone

        return self.status == "pending" and timezone.now() >= self.expires_at


class OptimizationAction(models.Model):
    """
    Immutable audit log of all executed optimization actions.

    Every action (manual-approved or autonomous) is recorded here
    with full before/after state and Meta API response.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="optimization_actions",
    )
    campaign = models.ForeignKey(
        CampaignRegistry,
        on_delete=models.CASCADE,
        related_name="actions",
    )
    recommendation = models.ForeignKey(
        OptimizationRecommendation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actions",
        help_text="Null for autonomous actions without prior recommendation",
    )
    action_id = models.UUIDField(default=uuid.uuid4, unique=True)

    action_type = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=20)
    entity_id = models.CharField(max_length=100)

    old_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)

    MODE_CHOICES = [
        ("manual", "Manual"),
        ("autonomous", "Autonomous"),
    ]
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    rationale = models.TextField()
    guardrails_applied = models.JSONField(default=list, blank=True)

    meta_api_response = models.JSONField(default=dict, blank=True)
    verified = models.BooleanField(default=False)
    verification_result = models.JSONField(default=dict, blank=True)

    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-executed_at"]
        indexes = [
            models.Index(
                fields=["tenant", "campaign"], name="idx_opt_action_tenant_campaign"
            ),
        ]

    def __str__(self):
        return f"{self.action_type} {self.entity_type}:{self.entity_id} ({self.mode})"
