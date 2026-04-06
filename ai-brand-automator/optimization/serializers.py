"""
Serializers for the optimization app.

Handles CampaignRegistry CRUD, OptimizationRecommendation approval flows,
and OptimizationAction audit log display.
"""

from rest_framework import serializers

from .models import CampaignRegistry, OptimizationAction, OptimizationRecommendation


class CampaignRegistrySerializer(serializers.ModelSerializer):
    """Full campaign registry detail."""

    age_days = serializers.ReadOnlyField()
    pending_recommendations_count = serializers.SerializerMethodField()

    class Meta:
        model = CampaignRegistry
        fields = [
            "id",
            "campaign_id",
            "meta_campaign_id",
            "meta_ad_account_id",
            "campaign_name",
            "objective",
            "status",
            "optimization_mode",
            "target_cpa_usd",
            "target_roas",
            "daily_budget_usd",
            "lifetime_budget_usd",
            "ad_sets",
            "ads",
            "start_date",
            "end_date",
            "guardrail_config",
            "source_job_id",
            "brand_context_id",
            "sandbox_mode",
            "age_days",
            "pending_recommendations_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "campaign_id",
            "age_days",
            "pending_recommendations_count",
            "created_at",
            "updated_at",
        ]

    def get_pending_recommendations_count(self, obj):
        return obj.recommendations.filter(status="pending").count()


class CampaignRegistryListSerializer(serializers.ModelSerializer):
    """Lightweight list view for campaigns."""

    age_days = serializers.ReadOnlyField()
    pending_recommendations_count = serializers.SerializerMethodField()

    class Meta:
        model = CampaignRegistry
        fields = [
            "id",
            "campaign_id",
            "campaign_name",
            "objective",
            "status",
            "optimization_mode",
            "daily_budget_usd",
            "target_cpa_usd",
            "target_roas",
            "sandbox_mode",
            "age_days",
            "pending_recommendations_count",
            "start_date",
            "created_at",
        ]

    def get_pending_recommendations_count(self, obj):
        return obj.recommendations.filter(status="pending").count()


class CampaignSettingsSerializer(serializers.Serializer):
    """For PATCH /campaigns/{id}/settings/ — update mode + guardrails."""

    optimization_mode = serializers.ChoiceField(
        choices=["manual", "autonomous"],
        required=False,
    )
    guardrail_config = serializers.DictField(required=False)


class OptimizationRecommendationSerializer(serializers.ModelSerializer):
    """Full recommendation detail."""

    campaign_name = serializers.CharField(
        source="campaign.campaign_name", read_only=True
    )
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = OptimizationRecommendation
        fields = [
            "id",
            "recommendation_id",
            "campaign",
            "campaign_name",
            "action_type",
            "entity_type",
            "entity_id",
            "current_values",
            "proposed_values",
            "rationale",
            "projected_impact",
            "priority",
            "status",
            "approved_by",
            "rejection_reason",
            "modified_values",
            "expires_at",
            "executed_at",
            "tick_id",
            "data_freshness",
            "guardrails_applied",
            "is_expired",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "recommendation_id",
            "campaign",
            "campaign_name",
            "is_expired",
            "created_at",
            "updated_at",
        ]


class ApproveRecommendationSerializer(serializers.Serializer):
    """For POST /recommendations/{rec_id}/approve/"""

    modified_values = serializers.DictField(required=False, default=dict)


class RejectRecommendationSerializer(serializers.Serializer):
    """For POST /recommendations/{rec_id}/reject/"""

    reason = serializers.CharField(required=False, default="", allow_blank=True)


class BatchApproveSerializer(serializers.Serializer):
    """For POST /campaigns/{id}/recommendations/approve-all/"""

    pass


class OptimizationActionSerializer(serializers.ModelSerializer):
    """Read-only audit log entry."""

    campaign_name = serializers.CharField(
        source="campaign.campaign_name", read_only=True
    )

    class Meta:
        model = OptimizationAction
        fields = [
            "id",
            "action_id",
            "campaign",
            "campaign_name",
            "recommendation",
            "action_type",
            "entity_type",
            "entity_id",
            "old_value",
            "new_value",
            "mode",
            "rationale",
            "guardrails_applied",
            "meta_api_response",
            "verified",
            "verification_result",
            "executed_at",
        ]
        read_only_fields = fields


class TickResultCallbackSerializer(serializers.Serializer):
    """
    Callback payload from COA service after each optimization tick.
    Authenticated via X-Callback-Token.
    """

    tick_id = serializers.CharField()
    tenant_id = serializers.CharField(allow_blank=True)
    campaign_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=["manual", "autonomous"])

    # Tick summary
    campaigns_processed = serializers.IntegerField(default=0)
    recommendations_generated = serializers.IntegerField(default=0)
    auto_actions_executed = serializers.IntegerField(default=0)

    # Performance metrics
    performance = serializers.DictField(required=False, default=dict)

    # Recommendations created
    recommendations = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    # Actions executed (autonomous mode)
    actions = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    # Fatigued ads
    fatigued_ads = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    # Campaign entity updates
    entity_updates = serializers.DictField(required=False, default=dict)
