"""URL configuration for the intelligence_loop app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CampaignIntelligenceViewSet,
    WF2RerunRequestViewSet,
    apply_learning,
    approve_wf2_request,
    auto_trigger_rerun,
    campaign_context,
    dismiss_learning,
    ingest_intelligence_report,
    ingest_rag_learning,
    ingest_wf2_request,
    reject_wf2_request,
    save_learning,
    trigger_extraction,
)

router = DefaultRouter()
router.register(
    r"intelligence-reports",
    CampaignIntelligenceViewSet,
    basename="intelligence-reports",
)
router.register(
    r"wf2-rerun-requests",
    WF2RerunRequestViewSet,
    basename="wf2-rerun-requests",
)


urlpatterns = [
    path("", include(router.urls)),
    # Learning actions
    path(
        "learnings/<uuid:learning_id>/apply/",
        apply_learning,
        name="ila-learning-apply",
    ),
    path(
        "learnings/<uuid:learning_id>/dismiss/",
        dismiss_learning,
        name="ila-learning-dismiss",
    ),
    path(
        "learnings/<uuid:learning_id>/save/",
        save_learning,
        name="ila-learning-save",
    ),
    # WF2 approval actions
    path(
        "wf2-rerun-requests/<uuid:request_id>/approve/",
        approve_wf2_request,
        name="ila-wf2-approve",
    ),
    path(
        "wf2-rerun-requests/<uuid:request_id>/reject/",
        reject_wf2_request,
        name="ila-wf2-reject",
    ),
    # Manual trigger (proxy to ILA service)
    path("trigger/", trigger_extraction, name="ila-trigger"),
    # Service-token ingest endpoints (called by ILA microservice)
    path(
        "ingest/intelligence-report/",
        ingest_intelligence_report,
        name="ila-ingest-intelligence-report",
    ),
    path(
        "ingest/rag-learning/",
        ingest_rag_learning,
        name="ila-ingest-rag-learning",
    ),
    path(
        "ingest/wf2-request/",
        ingest_wf2_request,
        name="ila-ingest-wf2-request",
    ),
    # Service-token campaign context loader (called by ILA microservice)
    path(
        "campaign-context/<uuid:campaign_id>/",
        campaign_context,
        name="ila-campaign-context",
    ),
    # Service-token auto-trigger (called by ILA microservice)
    path(
        "auto-trigger/",
        auto_trigger_rerun,
        name="ila-auto-trigger",
    ),
]
