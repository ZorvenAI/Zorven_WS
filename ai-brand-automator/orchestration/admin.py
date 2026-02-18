"""
Admin configuration for the orchestration app.
"""

from django.contrib import admin

from .models import AnalysisJob, PipelineManifest


@admin.register(PipelineManifest)
class PipelineManifestAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "pipeline_id",
        "version",
        "is_active",
        "tenant",
        "created_at",
    ]
    list_filter = ["is_active", "version"]
    search_fields = ["name", "pipeline_id", "description"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = [
        "job_id",
        "manifest",
        "status",
        "tenant",
        "created_by",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["job_id", "input_prompt"]
    readonly_fields = [
        "job_id",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    ]
