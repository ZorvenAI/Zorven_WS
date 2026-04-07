from django.contrib import admin

from .models import (
    CampaignIntelligence,
    LearningDocument,
    LearningRecord,
    WF2RerunRequest,
)


@admin.register(CampaignIntelligence)
class CampaignIntelligenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "campaign",
        "mode",
        "trigger_source",
        "auto_reruns_triggered",
        "rag_writes",
        "created_at",
    )
    list_filter = ("mode", "trigger_source", "created_at")
    search_fields = ("job_id", "campaign__campaign_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LearningRecord)
class LearningRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "category",
        "headline",
        "confidence",
        "impact",
        "target_workflow",
        "target_agent",
        "status",
        "created_at",
    )
    list_filter = ("category", "impact", "status", "target_workflow")
    search_fields = ("headline",)
    readonly_fields = ("created_at",)


@admin.register(WF2RerunRequest)
class WF2RerunRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "learning",
        "requested_agent",
        "status",
        "decided_by",
        "decided_at",
        "expires_at",
        "created_at",
    )
    list_filter = ("status", "requested_agent")
    readonly_fields = ("created_at",)


@admin.register(LearningDocument)
class LearningDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "learning", "vector_doc_id", "created_at")
    search_fields = ("vector_doc_id",)
    readonly_fields = ("created_at",)
