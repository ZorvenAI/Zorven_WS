"""
Admin configuration for the automation app.
"""

from django.contrib import admin
from .models import (
    SocialProfile,
    AutomationTask,
    ContentCalendar,
    GoogleBusinessProfile,
    GoogleBusinessLocation,
)


@admin.register(SocialProfile)
class SocialProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "profile_name", "status", "created_at"]
    list_filter = ["platform", "status"]
    search_fields = ["user__email", "profile_name"]
    readonly_fields = ["created_at", "updated_at", "last_synced_at"]


@admin.register(AutomationTask)
class AutomationTaskAdmin(admin.ModelAdmin):
    list_display = ["user", "task_type", "status", "scheduled_at", "created_at"]
    list_filter = ["task_type", "status"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at", "started_at", "completed_at"]


@admin.register(ContentCalendar)
class ContentCalendarAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "status", "scheduled_date", "created_at"]
    list_filter = ["status", "platforms"]
    search_fields = ["title", "user__email", "content"]
    readonly_fields = ["created_at", "updated_at", "published_at"]


@admin.register(GoogleBusinessProfile)
class GoogleBusinessProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "google_email",
        "gbp_account_name",
        "status",
        "is_mock",
        "created_at",
    ]
    list_filter = ["status", "is_mock"]
    search_fields = ["user__email", "google_email", "gbp_account_name"]
    readonly_fields = ["created_at", "updated_at", "last_synced_at"]


@admin.register(GoogleBusinessLocation)
class GoogleBusinessLocationAdmin(admin.ModelAdmin):
    list_display = [
        "business_name",
        "city",
        "state",
        "primary_category",
        "verification_status",
        "created_at",
    ]
    list_filter = ["verification_status", "state", "country"]
    search_fields = ["business_name", "city", "primary_category"]
    readonly_fields = ["created_at", "updated_at", "last_synced_at", "location_id"]
