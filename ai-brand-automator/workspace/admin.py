from django.contrib import admin

from .models import ChatWorkspaceLink, UserWorkflow, WorkflowSnapshot


@admin.register(UserWorkflow)
class UserWorkflowAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "workflow_id",
        "source",
        "is_active",
        "is_favorite",
        "execution_count",
        "tenant",
        "created_by",
        "created_at",
    ]
    list_filter = ["source", "is_active", "is_favorite"]
    search_fields = ["name", "workflow_id", "description"]
    readonly_fields = ["workflow_id", "created_at", "updated_at"]


@admin.register(WorkflowSnapshot)
class WorkflowSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "snapshot_id",
        "workflow",
        "job",
        "tenant",
        "created_at",
    ]
    search_fields = ["snapshot_id"]
    readonly_fields = ["snapshot_id", "created_at"]


@admin.register(ChatWorkspaceLink)
class ChatWorkspaceLinkAdmin(admin.ModelAdmin):
    list_display = [
        "job",
        "workflow",
        "chat_session_id",
        "tenant",
        "created_at",
    ]
    search_fields = ["chat_session_id"]
    readonly_fields = ["created_at"]
