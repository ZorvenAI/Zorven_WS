from django.contrib import admin

from .models import CampaignRegistry, OptimizationAction, OptimizationRecommendation


@admin.register(CampaignRegistry)
class CampaignRegistryAdmin(admin.ModelAdmin):
    list_display = [
        "campaign_name",
        "meta_campaign_id",
        "status",
        "optimization_mode",
        "daily_budget_usd",
        "sandbox_mode",
        "created_at",
    ]
    list_filter = ["status", "optimization_mode", "sandbox_mode"]
    search_fields = ["campaign_name", "meta_campaign_id"]
    readonly_fields = ["campaign_id", "created_at", "updated_at"]


@admin.register(OptimizationRecommendation)
class OptimizationRecommendationAdmin(admin.ModelAdmin):
    list_display = [
        "action_type",
        "entity_type",
        "entity_id",
        "priority",
        "status",
        "expires_at",
        "created_at",
    ]
    list_filter = ["action_type", "priority", "status"]
    search_fields = ["entity_id", "tick_id"]
    readonly_fields = ["recommendation_id", "created_at", "updated_at"]


@admin.register(OptimizationAction)
class OptimizationActionAdmin(admin.ModelAdmin):
    list_display = [
        "action_type",
        "entity_type",
        "entity_id",
        "mode",
        "verified",
        "executed_at",
    ]
    list_filter = ["action_type", "mode", "verified"]
    search_fields = ["entity_id", "action_id"]
    readonly_fields = ["action_id", "executed_at"]
