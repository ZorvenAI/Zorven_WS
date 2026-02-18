"""
URL configuration for the orchestration app.

Routes registered via DRF DefaultRouter:
    /jobs/                  — AnalysisJobViewSet
    /manifests/             — PipelineManifestViewSet
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
    path("", include(router.urls)),
]
