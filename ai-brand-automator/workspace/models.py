"""
Models for the workspace app.

UserWorkflow — user-created or cloned workflow with layout metadata.
WorkflowSnapshot — frozen manifest + layout at execution time.
ChatWorkspaceLink — links a chat-dispatched job to a workspace workflow.
"""

import uuid

from django.conf import settings
from django.db import models


class UserWorkflow(models.Model):
    """
    A user-owned workflow with visual layout metadata.

    Each workflow wraps a PipelineManifest (the execution DAG) and adds
    layout_data (React Flow node positions + viewport) for the canvas editor.
    """

    class Source(models.TextChoices):
        CREATED = "created", "Created"
        CLONED = "cloned", "Cloned"
        TEMPLATE = "template", "Template"
        CHAT = "chat", "From Chat"

    workflow_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    manifest = models.ForeignKey(
        "orchestration.PipelineManifest",
        on_delete=models.CASCADE,
        related_name="user_workflows",
    )
    layout_data = models.JSONField(
        default=dict,
        help_text=(
            "React Flow positions: " "{nodes: {id: {x, y}}, viewport: {x, y, zoom}}"
        ),
    )
    is_favorite = models.BooleanField(default=False)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.CREATED,
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_workflows",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_workflows",
    )
    is_active = models.BooleanField(default=True)
    last_executed_at = models.DateTimeField(null=True, blank=True)
    execution_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"],
                condition=models.Q(is_active=True),
                name="unique_active_workflow_name_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.workflow_id})"


class WorkflowSnapshot(models.Model):
    """
    Frozen state of a workflow at execution time.

    Captures the manifest_data and layout_data so that historical
    executions can be replayed / compared even after the workflow
    is edited.
    """

    snapshot_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    workflow = models.ForeignKey(
        UserWorkflow,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    job = models.OneToOneField(
        "orchestration.AnalysisJob",
        on_delete=models.CASCADE,
        related_name="workflow_snapshot",
    )
    manifest_snapshot = models.JSONField(
        help_text="Frozen manifest_data at execution time",
    )
    layout_snapshot = models.JSONField(
        help_text="Frozen layout_data at execution time",
    )
    summary = models.JSONField(
        default=dict,
        help_text="Executive summary text",
    )
    dashboard_data = models.JSONField(
        default=dict,
        help_text=(
            "Hybrid KPI data: " "{typed: {voc_health_score, nps, ...}, generic: {k: v}}"
        ),
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_snapshots",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Snapshot {self.snapshot_id} for {self.workflow.name}"


class ChatWorkspaceLink(models.Model):
    """
    Links a chat-dispatched AnalysisJob to a workspace workflow.

    Enables bidirectional navigation: Chat -> Workspace and
    Workspace -> Chat.
    """

    job = models.OneToOneField(
        "orchestration.AnalysisJob",
        on_delete=models.CASCADE,
        related_name="workspace_link",
    )
    workflow = models.ForeignKey(
        UserWorkflow,
        on_delete=models.CASCADE,
        related_name="chat_links",
    )
    snapshot = models.ForeignKey(
        WorkflowSnapshot,
        null=True,
        on_delete=models.SET_NULL,
    )
    chat_session_id = models.CharField(max_length=100)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workspace_chat_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ChatLink {self.job.job_id} -> {self.workflow.name}"
