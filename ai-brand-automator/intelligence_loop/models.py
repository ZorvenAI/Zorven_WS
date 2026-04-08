"""
Models for the Intelligence Loop Agent (ILA, WF3.5).

Persistence layer for the agent that extracts strategic learnings from
campaign performance and feeds them back into WF1 (research) and WF2
(strategy) workflows. Models live in the shared schema with a nullable
``tenant`` FK to mirror the rest of the platform.

CampaignIntelligence — one row per ILA run (Intelligence Feed UI source).
LearningRecord       — individual strategic learning extracted by ILA.
WF2RerunRequest      — pending human-approval request to re-run a WF2 agent.
LearningDocument     — RAG-bound copy of a learning, synced to Vertex AI by
                       ``rag_index`` signals + db_sync_tasks.
"""

import uuid

from django.conf import settings
from django.db import models


class CampaignIntelligence(models.Model):
    """One row per ILA run for a campaign (Intelligence Feed UI source)."""

    MODE_CHOICES = [
        ("store_only", "Store Only"),
        ("auto_trigger", "Auto Trigger"),
    ]
    TRIGGER_SOURCE_CHOICES = [
        ("kafka_completed", "Kafka campaign.completed"),
        ("coa_event", "COA action_executed"),
        ("weekly_tick", "Celery Beat weekly tick"),
        ("manual", "Manual / on-demand"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="intelligence_reports",
    )
    campaign = models.ForeignKey(
        "optimization.CampaignRegistry",
        on_delete=models.CASCADE,
        related_name="intelligence_reports",
    )
    intelligence_id = models.UUIDField(default=uuid.uuid4, unique=True)
    job_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="ILA run id (orchestrator job_id or internal uuid).",
    )
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default="store_only")
    trigger_source = models.CharField(
        max_length=32, choices=TRIGGER_SOURCE_CHOICES, default="manual"
    )

    intelligence_report = models.JSONField(
        default=dict,
        blank=True,
        help_text="Synthesized narrative + summary from ILA scorer.",
    )
    auto_reruns_triggered = models.PositiveIntegerField(default=0)
    contradictions = models.JSONField(default=list, blank=True)
    rag_writes = models.PositiveIntegerField(default=0)

    brand_context_id = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "-created_at"],
                name="idx_ila_intel_tenant_created",
            ),
            models.Index(
                fields=["campaign", "-created_at"],
                name="idx_ila_intel_camp_created",
            ),
        ]

    def __str__(self):
        return f"Intelligence({self.campaign_id}, {self.created_at:%Y-%m-%d})"


class LearningRecord(models.Model):
    """Individual strategic learning extracted by ILA."""

    CATEGORY_CHOICES = [
        ("audience", "Audience"),
        ("messaging", "Messaging"),
        ("creative", "Creative"),
        ("funnel", "Funnel"),
        ("competitive", "Competitive"),
    ]
    IMPACT_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
    ]
    STATUS_CHOICES = [
        ("new", "New"),
        ("applied", "Applied"),
        ("dismissed", "Dismissed"),
        ("saved", "Saved"),
    ]
    WORKFLOW_CHOICES = [
        ("WF1", "Workflow 1 — Research"),
        ("WF2", "Workflow 2 — Strategy"),
        ("WF3", "Workflow 3 — Campaigns"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="learning_records",
    )
    intelligence = models.ForeignKey(
        CampaignIntelligence,
        on_delete=models.CASCADE,
        related_name="learnings",
    )
    learning_id = models.UUIDField(default=uuid.uuid4, unique=True)

    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES)
    headline = models.CharField(max_length=500)
    detail = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured payload + evidence + sample_size.",
    )

    confidence = models.PositiveSmallIntegerField(
        help_text="Final scored confidence (0-100)."
    )
    impact = models.CharField(max_length=8, choices=IMPACT_CHOICES)

    target_workflow = models.CharField(max_length=8, choices=WORKFLOW_CHOICES)
    target_agent = models.CharField(
        max_length=16,
        help_text="Target agent code (APA, BPA, BPV, NTA, BSA, CAA, CIA…).",
    )

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="new")
    rag_document_id = models.CharField(max_length=128, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "category", "status"],
                name="idx_ila_learn_tenant_cat",
            ),
            models.Index(
                fields=["intelligence", "category"],
                name="idx_ila_learn_intel_cat",
            ),
        ]

    def __str__(self):
        return f"{self.category}:{self.headline[:60]}"


class WF2RerunRequest(models.Model):
    """Pending human-approval record for a WF2 strategy re-run."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="wf2_rerun_requests",
    )
    learning = models.ForeignKey(
        LearningRecord,
        on_delete=models.CASCADE,
        related_name="wf2_rerun_requests",
    )
    request_id = models.UUIDField(default=uuid.uuid4, unique=True)

    requested_agent = models.CharField(
        max_length=16, help_text="WF2 agent code (BPA|BAA|BPV|NTA|BSA)."
    )
    rationale = models.TextField()

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    requested_by = models.CharField(max_length=64, default="ila")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wf2_rerun_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    expires_at = models.DateTimeField(
        help_text="Auto-expire after ILA_WF2_APPROVAL_TIMEOUT_HOURS (default 72h)."
    )
    job_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="AnalysisJob id once dispatched on approval.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="idx_ila_wf2req_tenant_status",
            ),
        ]

    def __str__(self):
        return f"WF2RerunRequest({self.requested_agent}, {self.status})"

    @property
    def is_expired(self):
        from django.utils import timezone

        return self.status == "pending" and timezone.now() >= self.expires_at


class LearningDocument(models.Model):
    """RAG-bound copy of a learning.

    Synced to per-tenant Vertex AI data stores by ``rag_index`` signals
    and ``rag_index.tasks.db_sync_tasks.sync_model_to_rag``.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="learning_documents",
    )
    learning = models.OneToOneField(
        LearningRecord,
        on_delete=models.CASCADE,
        related_name="rag_document",
    )

    content = models.TextField(help_text="Retrieval text written into RAG.")
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Structured metadata used as Vertex AI document filters: "
            "category, impact, confidence, campaign_id, brand_context_id."
        ),
    )
    vector_doc_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Vertex AI document ID, populated by sync task.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"LearningDocument(learning={self.learning.learning_id})"
