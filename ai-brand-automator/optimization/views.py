"""
Views for the optimization app.

CampaignRegistryViewSet — CRUD for campaign registry entries.
Includes callback endpoint for COA tick results and recommendation approval flows.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from tenants.permissions import (
    IsTenantAdmin,
    IsTenantEditor,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)

from .models import CampaignRegistry, OptimizationAction, OptimizationRecommendation
from .serializers import (
    ApproveRecommendationSerializer,
    CampaignRegistryListSerializer,
    CampaignRegistrySerializer,
    CampaignSettingsSerializer,
    OptimizationActionSerializer,
    OptimizationRecommendationSerializer,
    RejectRecommendationSerializer,
    TickResultCallbackSerializer,
)

logger = logging.getLogger(__name__)


class CampaignRegistryViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing campaign registry entries.

    Endpoints:
        GET    /campaigns/                         — List active campaigns
        GET    /campaigns/{campaign_id}/            — Campaign detail
        PATCH  /campaigns/{campaign_id}/settings/   — Update mode + guardrails
        GET    /campaigns/{campaign_id}/recommendations/ — Pending recommendations
        POST   /campaigns/{campaign_id}/recommendations/{rec_id}/approve/
        POST   /campaigns/{campaign_id}/recommendations/{rec_id}/reject/
        POST   /campaigns/{campaign_id}/recommendations/approve-all/
        GET    /campaigns/{campaign_id}/actions/    — Action audit log
    """

    serializer_class = CampaignRegistrySerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "campaign_id"
    http_method_names = ["get", "post", "patch", "head", "options"]

    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "partial_update": [IsAuthenticated, IsTenantAdmin],
        "update_settings": [IsAuthenticated, IsTenantAdmin],
        "recommendations": [IsAuthenticated, IsTenantViewer],
        "approve": [IsAuthenticated, IsTenantAdmin],
        "reject": [IsAuthenticated, IsTenantEditor],
        "approve_all": [IsAuthenticated, IsTenantAdmin],
        "actions": [IsAuthenticated, IsTenantViewer],
    }

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        qs = CampaignRegistry.objects.select_related("company")
        if tenant:
            qs = qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
        else:
            qs = qs.filter(tenant__isnull=True)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return CampaignRegistryListSerializer
        if self.action == "settings":
            return CampaignSettingsSerializer
        return CampaignRegistrySerializer

    @action(detail=True, methods=["patch"], url_path="settings")
    def update_settings(self, request, campaign_id=None):
        """Update optimization mode and guardrail configuration."""
        campaign = self.get_object()
        serializer = CampaignSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        update_fields = ["updated_at"]

        if "optimization_mode" in serializer.validated_data:
            campaign.optimization_mode = serializer.validated_data["optimization_mode"]
            update_fields.append("optimization_mode")

        if "guardrail_config" in serializer.validated_data:
            campaign.guardrail_config = serializer.validated_data["guardrail_config"]
            update_fields.append("guardrail_config")

        campaign.save(update_fields=update_fields)

        return Response(
            CampaignRegistrySerializer(campaign).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="recommendations")
    def recommendations(self, request, campaign_id=None):
        """List recommendations for a campaign, optionally filtered by status."""
        campaign = self.get_object()
        rec_status = request.query_params.get("status", "pending")

        recs = OptimizationRecommendation.objects.filter(
            campaign=campaign,
        )
        if rec_status != "all":
            recs = recs.filter(status=rec_status)

        serializer = OptimizationRecommendationSerializer(recs, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"recommendations/(?P<rec_id>[^/.]+)/approve",
    )
    def approve(self, request, campaign_id=None, rec_id=None):
        """Approve a recommendation, optionally with modified values."""
        campaign = self.get_object()
        serializer = ApproveRecommendationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                rec = OptimizationRecommendation.objects.select_for_update().get(
                    campaign=campaign,
                    recommendation_id=rec_id,
                    status="pending",
                )

                if rec.is_expired:
                    rec.status = "expired"
                    rec.save(update_fields=["status", "updated_at"])
                    return Response(
                        {"error": "Recommendation has expired"},
                        status=status.HTTP_410_GONE,
                    )

                modified = serializer.validated_data.get("modified_values", {})
                if modified:
                    rec.status = "modified"
                    rec.modified_values = modified
                else:
                    rec.status = "approved"

                rec.approved_by = str(getattr(request.user, "id", ""))
                rec.save(
                    update_fields=[
                        "status",
                        "approved_by",
                        "modified_values",
                        "updated_at",
                    ]
                )

        except OptimizationRecommendation.DoesNotExist:
            return Response(
                {"error": "Recommendation not found or not pending"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # TODO: Proxy the approved action to COA service at :8044
        # for Meta API execution. For now, just mark as approved.

        return Response(
            OptimizationRecommendationSerializer(rec).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path=r"recommendations/(?P<rec_id>[^/.]+)/reject",
    )
    def reject(self, request, campaign_id=None, rec_id=None):
        """Reject a recommendation with optional reason."""
        campaign = self.get_object()
        serializer = RejectRecommendationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                rec = OptimizationRecommendation.objects.select_for_update().get(
                    campaign=campaign,
                    recommendation_id=rec_id,
                    status="pending",
                )
                rec.status = "rejected"
                rec.rejection_reason = serializer.validated_data.get("reason", "")
                rec.save(update_fields=["status", "rejection_reason", "updated_at"])

        except OptimizationRecommendation.DoesNotExist:
            return Response(
                {"error": "Recommendation not found or not pending"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            OptimizationRecommendationSerializer(rec).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="recommendations/approve-all",
    )
    def approve_all(self, request, campaign_id=None):
        """Batch approve all pending recommendations for a campaign."""
        campaign = self.get_object()

        now = timezone.now()
        with transaction.atomic():
            # Expire any that are past their expiry
            expired_count = OptimizationRecommendation.objects.filter(
                campaign=campaign,
                status="pending",
                expires_at__lt=now,
            ).update(status="expired")

            # Approve remaining pending
            approved_count = OptimizationRecommendation.objects.filter(
                campaign=campaign,
                status="pending",
            ).update(
                status="approved",
                approved_by=str(getattr(request.user, "id", "")),
            )

        return Response(
            {
                "approved_count": approved_count,
                "expired_count": expired_count,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="actions")
    def actions(self, request, campaign_id=None):
        """List executed optimization actions for audit."""
        campaign = self.get_object()
        actions_qs = OptimizationAction.objects.filter(campaign=campaign)

        # Optional filters
        action_type = request.query_params.get("action_type")
        mode = request.query_params.get("mode")
        if action_type:
            actions_qs = actions_qs.filter(action_type=action_type)
        if mode:
            actions_qs = actions_qs.filter(mode=mode)

        serializer = OptimizationActionSerializer(actions_qs[:100], many=True)
        return Response(serializer.data)


@api_view(["POST"])
@permission_classes([AllowAny])
def optimization_tick_callback(request):
    """
    Callback endpoint for the Continuous Optimization Agent (COA).

    Authenticates via X-Callback-Token header (service-to-service).
    Receives tick results and persists recommendations/actions to Django models.
    """
    # Verify callback token
    token = request.META.get("HTTP_X_CALLBACK_TOKEN", "")
    expected_token = getattr(settings, "ORCHESTRATOR_CALLBACK_TOKEN", "")
    if not expected_token or token != expected_token:
        logger.warning("Invalid callback token for optimization tick")
        return Response(
            {"error": "Invalid callback token"},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = TickResultCallbackSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    campaign_id = data["campaign_id"]

    try:
        campaign = CampaignRegistry.objects.get(campaign_id=campaign_id)
    except CampaignRegistry.DoesNotExist:
        logger.error("Campaign %s not found for tick callback", campaign_id)
        return Response(
            {"error": "Campaign not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Persist recommendations from this tick
    recs_created = 0
    for rec_data in data.get("recommendations", []):
        try:
            OptimizationRecommendation.objects.create(
                tenant=campaign.tenant,
                campaign=campaign,
                action_type=rec_data.get("action_type", "PAUSE"),
                entity_type=rec_data.get("entity_type", "ad_set"),
                entity_id=rec_data.get("entity_id", ""),
                current_values=rec_data.get("current_values", {}),
                proposed_values=rec_data.get("proposed_values", {}),
                rationale=rec_data.get("rationale", ""),
                projected_impact=rec_data.get("projected_impact", {}),
                priority=rec_data.get("priority", "MEDIUM"),
                tick_id=data["tick_id"],
                data_freshness=rec_data.get("data_freshness", timezone.now()),
                guardrails_applied=rec_data.get("guardrails_applied", []),
                expires_at=rec_data.get(
                    "expires_at",
                    timezone.now() + timezone.timedelta(hours=48),
                ),
            )
            recs_created += 1
        except Exception:
            logger.exception(
                "Failed to create recommendation for campaign %s", campaign_id
            )

    # Persist executed actions from this tick
    actions_created = 0
    for action_data in data.get("actions", []):
        try:
            # Link to recommendation if available
            rec = None
            rec_id = action_data.get("recommendation_id")
            if rec_id:
                rec = OptimizationRecommendation.objects.filter(
                    recommendation_id=rec_id
                ).first()

            OptimizationAction.objects.create(
                tenant=campaign.tenant,
                campaign=campaign,
                recommendation=rec,
                action_type=action_data.get("action_type", ""),
                entity_type=action_data.get("entity_type", ""),
                entity_id=action_data.get("entity_id", ""),
                old_value=action_data.get("old_value", {}),
                new_value=action_data.get("new_value", {}),
                mode=data["mode"],
                rationale=action_data.get("rationale", ""),
                guardrails_applied=action_data.get("guardrails_applied", []),
                meta_api_response=action_data.get("meta_api_response", {}),
                verified=action_data.get("verified", False),
                verification_result=action_data.get("verification_result", {}),
            )
            actions_created += 1
        except Exception:
            logger.exception("Failed to create action for campaign %s", campaign_id)

    # Update campaign entity tree if provided
    entity_updates = data.get("entity_updates", {})
    if entity_updates:
        update_fields = ["updated_at"]
        if "ad_sets" in entity_updates:
            campaign.ad_sets = entity_updates["ad_sets"]
            update_fields.append("ad_sets")
        if "ads" in entity_updates:
            campaign.ads = entity_updates["ads"]
            update_fields.append("ads")
        if "status" in entity_updates:
            campaign.status = entity_updates["status"]
            update_fields.append("status")
        campaign.save(update_fields=update_fields)

    logger.info(
        "Optimization tick callback: campaign=%s recs=%d actions=%d",
        campaign_id,
        recs_created,
        actions_created,
    )

    return Response(
        {
            "status": "ok",
            "recommendations_created": recs_created,
            "actions_created": actions_created,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def register_campaign(request):
    """
    Service-to-service registration endpoint for the Ad Publishing Agent
    (APA-3.3) to register a freshly published Meta campaign for continuous
    optimization (COA-3.4). Authenticates via X-Callback-Token.

    Expected payload:
        {
            "tenant_id": "<uuid or empty>",
            "company_id": <int or null>,
            "meta_campaign_id": "...",
            "meta_ad_account_id": "...",
            "campaign_name": "...",
            "objective": "...",
            "daily_budget_usd": 50.0,
            "lifetime_budget_usd": null,
            "target_cpa_usd": null,
            "target_roas": null,
            "ad_sets": [...],
            "ads": [...],
            "source_job_id": "<uuid or null>",
            "sandbox_mode": true,
            "optimization_mode": "manual"
        }
    """
    # Accept either X-Service-Token or X-Callback-Token (different
    # service-to-service callers may use different conventions).
    service_token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    callback_token = request.META.get("HTTP_X_CALLBACK_TOKEN", "")
    expected_service = getattr(settings, "ORCHESTRATOR_SERVICE_TOKEN", "")
    expected_callback = getattr(settings, "ORCHESTRATOR_CALLBACK_TOKEN", "")
    valid = (expected_service and service_token == expected_service) or (
        expected_callback and callback_token == expected_callback
    )
    if not valid:
        logger.warning("Invalid token for campaign registration")
        return Response(
            {"error": "Invalid token"},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = request.data or {}
    meta_campaign_id = data.get("meta_campaign_id", "")
    if not meta_campaign_id:
        return Response(
            {"error": "meta_campaign_id required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Resolve tenant
    tenant = None
    tenant_id = data.get("tenant_id") or ""
    if tenant_id:
        try:
            from tenants.models import Tenant

            tenant = Tenant.objects.filter(id=tenant_id).first()
        except Exception:
            tenant = None

    # Resolve company
    company = None
    company_id = data.get("company_id")
    if company_id:
        try:
            from onboarding.models import Company

            company = Company.objects.filter(id=company_id).first()
        except Exception:
            company = None

    defaults = {
        "tenant": tenant,
        "company": company,
        "meta_ad_account_id": data.get("meta_ad_account_id", ""),
        "campaign_name": data.get("campaign_name", "Unnamed Campaign"),
        "objective": data.get("objective", ""),
        "status": data.get("status", "active"),
        "optimization_mode": data.get("optimization_mode", "manual"),
        "target_cpa_usd": data.get("target_cpa_usd"),
        "target_roas": data.get("target_roas"),
        "daily_budget_usd": data.get("daily_budget_usd") or 0,
        "lifetime_budget_usd": data.get("lifetime_budget_usd"),
        "ad_sets": data.get("ad_sets", []),
        "ads": data.get("ads", []),
        "start_date": data.get("start_date", timezone.now()),
        "source_job_id": data.get("source_job_id") or None,
        "brand_context_id": data.get("brand_context_id", ""),
        "sandbox_mode": data.get("sandbox_mode", True),
    }

    try:
        campaign, created = CampaignRegistry.objects.update_or_create(
            tenant=tenant,
            meta_campaign_id=meta_campaign_id,
            defaults=defaults,
        )
    except Exception:
        logger.exception(
            "Failed to register campaign meta_campaign_id=%s", meta_campaign_id
        )
        return Response(
            {"error": "Failed to register campaign"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.info(
        "Campaign registered for optimization: meta=%s internal=%s created=%s",
        meta_campaign_id,
        campaign.campaign_id,
        created,
    )

    return Response(
        {
            "status": "ok",
            "created": created,
            "campaign_id": str(campaign.campaign_id),
            "meta_campaign_id": meta_campaign_id,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )
