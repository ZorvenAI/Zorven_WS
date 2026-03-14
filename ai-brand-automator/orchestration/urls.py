"""
URL configuration for the orchestration app.

Routes registered via DRF DefaultRouter:
    /jobs/                  — AnalysisJobViewSet
    /manifests/             — PipelineManifestViewSet
    /callback-debug/        — Diagnostic callback endpoint (X-Service-Token auth)
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"jobs", views.AnalysisJobViewSet, basename="analysis-job")
router.register(
    r"manifests",
    views.PipelineManifestViewSet,
    basename="pipeline-manifest",
)

urlpatterns = [
    path("callback-debug/", views.callback_debug, name="callback-debug"),
    path(
        "notifications/push/",
        views.push_notification,
        name="push-notification",
    ),
    path("", include(router.urls)),
]
