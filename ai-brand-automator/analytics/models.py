from django.db import models


class MetricSnapshot(models.Model):
    """Per-execution metric record — one row per metric per job."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="metric_snapshots",
        db_index=True,
    )
    job = models.ForeignKey(
        "orchestration.AnalysisJob",
        on_delete=models.CASCADE,
        related_name="metrics",
    )
    pipeline_id = models.SlugField(max_length=100, db_index=True)
    metric_name = models.CharField(max_length=100, db_index=True)
    metric_value = models.FloatField()
    metric_unit = models.CharField(max_length=20, default="score")
    metric_category = models.CharField(max_length=50, db_index=True)
    agent_source = models.CharField(max_length=100, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-recorded_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "job", "metric_name"],
                name="unique_snap_tenant_job_metric",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "pipeline_id", "metric_name", "recorded_at"],
                name="idx_snap_tnt_pipe_metric",
            ),
            models.Index(
                fields=["tenant", "metric_category", "recorded_at"],
                name="idx_snap_tnt_category",
            ),
        ]

    def __str__(self):
        return f"{self.metric_name}={self.metric_value} (job={self.job_id})"


class MetricRollup(models.Model):
    """Pre-aggregated time buckets for fast dashboard queries."""

    class Period(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    class TrendDirection(models.TextChoices):
        IMPROVING = "improving", "Improving"
        STABLE = "stable", "Stable"
        DECLINING = "declining", "Declining"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="metric_rollups",
    )
    pipeline_id = models.SlugField(max_length=100)
    metric_name = models.CharField(max_length=100)
    metric_category = models.CharField(max_length=50)
    period = models.CharField(max_length=10, choices=Period.choices)
    period_start = models.DateField(db_index=True)
    avg_value = models.FloatField()
    min_value = models.FloatField()
    max_value = models.FloatField()
    latest_value = models.FloatField()
    sample_count = models.PositiveIntegerField()
    trend_direction = models.CharField(
        max_length=10,
        choices=TrendDirection.choices,
        default=TrendDirection.STABLE,
    )
    change_pct = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "tenant",
                    "pipeline_id",
                    "metric_name",
                    "period",
                    "period_start",
                ],
                name="unique_rollup_tenant_pipe_metric_period",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "period", "period_start"],
                name="idx_rollup_tenant_period",
            ),
        ]

    def __str__(self):
        return (
            f"{self.metric_name} {self.period} "
            f"{self.period_start} avg={self.avg_value}"
        )


class MetricDefinition(models.Model):
    """Metric registry — seeded via management command."""

    metric_name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    category = models.CharField(max_length=50)
    unit = models.CharField(max_length=20)
    value_range_min = models.FloatField(default=0)
    value_range_max = models.FloatField(default=100)
    higher_is_better = models.BooleanField(default=True)
    chart_color = models.CharField(max_length=7, default="#00F5FF")
    display_order = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True, default="")
    source_pipelines = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "metric_name"]

    def __str__(self):
        return f"{self.display_name} ({self.metric_name})"
