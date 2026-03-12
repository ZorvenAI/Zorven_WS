"""
Models for the orchestration app.

PipelineManifest — reusable pipeline template (LangGraph-compatible).
AnalysisJob — tracks a single pipeline execution lifecycle.
CompetitorProfile — persistent competitor registry (PostgreSQL backup for Redis).
CompetitorSnapshot — point-in-time snapshot of a competitor profile.
"""

import uuid

from django.conf import settings
from django.db import models


class PipelineManifest(models.Model):
    """
    A reusable pipeline definition (LangGraph-compatible).

    The manifest_data JSONB stores the full pipeline graph using
    the HLD v6.0 "Pipeline-as-Code" node format:
    {
        "pipeline_id": "iso-brand-equity-v1",
        "nodes": [
            {
                "id": "intent_router",
                "type": "internal",
                "handler": "RouterNode",
                "config": {}
            },
            {
                "id": "web_research",
                "type": "external",
                "url": "http://discovery-agent-svc:8020/v1/search",
                "config": {"timeout": 60}
            }
        ],
        "edges": [
            ["intent_router", "web_research"]
        ],
        "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7}
    }

    Node types:
    - "internal": Handled within the orchestrator (e.g., RouterNode)
    - "external": REST call to a separate agent microservice (has "url")
    """

    pipeline_id = models.SlugField(
        max_length=100,
        help_text="Human-readable identifier (e.g., 'brand-analysis-v1')",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    manifest_data = models.JSONField(
        help_text=(
            "LangGraph-compatible pipeline definition " "(agents, edges, config)"
        ),
    )
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pipeline_manifests",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_manifests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["pipeline_id", "version"],
                name="unique_pipeline_version",
            ),
        ]

    def __str__(self):
        return f"{self.name} v{self.version} ({self.pipeline_id})"


class AnalysisJob(models.Model):
    """
    Tracks a single pipeline execution.

    Lifecycle: QUEUED -> RUNNING -> COMPLETED / FAILED
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    job_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="analysis_jobs",
    )
    manifest = models.ForeignKey(
        PipelineManifest,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="jobs",
    )
    input_prompt = models.TextField(
        help_text="User's natural language analysis request",
    )
    input_context = models.JSONField(
        default=dict,
        blank=True,
        help_text=("Additional context (company_id, brand assets, etc.)"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    progress = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-agent progress: " "{'agent_id': {'status': 'done', 'output': {...}}}"
        ),
    )
    result_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Final aggregated results from the pipeline",
    )
    error_message = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analysis_jobs",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job {self.job_id} ({self.status})"

    @property
    def duration_seconds(self):
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class CompetitorProfile(models.Model):
    """
    Persistent competitor profile — PostgreSQL backup for CIA's Redis registry.

    Synced from competitor-intel-agent-svc via HTTP callback. Each record
    represents a single competitor tracked for a specific tenant.
    """

    class CompetitorType(models.TextChoices):
        DIRECT = "direct", "Direct Competitor"
        INDIRECT = "indirect", "Indirect Competitor"
        EMERGING = "emerging", "Emerging Competitor"
        SUBSTITUTE = "substitute", "Substitute"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="competitor_profiles",
    )
    slug = models.SlugField(
        max_length=200,
        help_text="URL-safe identifier (e.g., 'acme-corp')",
    )
    name = models.CharField(max_length=300)
    website = models.URLField(max_length=500, blank=True, default="")
    competitor_type = models.CharField(
        max_length=20,
        choices=CompetitorType.choices,
        default=CompetitorType.DIRECT,
    )
    discovered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this competitor was first identified",
    )
    last_profiled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time a full profile scan was run",
    )
    profile_version = models.PositiveIntegerField(default=1)
    profile_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full competitor profile data from CIA",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="unique_competitor_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class CompetitorSnapshot(models.Model):
    """
    Point-in-time snapshot of a competitor profile for change detection.

    CIA creates snapshots after each profiling run (90-day TTL in Redis).
    PostgreSQL stores them permanently for audit trail and trend analysis.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="competitor_snapshots",
    )
    competitor = models.ForeignKey(
        CompetitorProfile,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    snapshot_date = models.DateField(
        help_text="Date this snapshot represents",
    )
    snapshot_data = models.JSONField(
        default=dict,
        help_text="Full profile data at time of snapshot",
    )
    changes_detected = models.JSONField(
        default=dict,
        blank=True,
        help_text="Changes vs. previous snapshot",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-snapshot_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["competitor", "snapshot_date"],
                name="unique_snapshot_per_day",
            ),
        ]

    def __str__(self):
        return f"Snapshot {self.competitor.slug} @ {self.snapshot_date}"
