"""
URL routing for Media Curation API.

Provides REST endpoints for the media curation service:
- POST /api/v1/curation/ - Submit content for curation
- POST /api/v1/curation/batch/ - Submit batch curation request
- POST /api/v1/curation/sync/ - Synchronous curation (testing)
- GET /api/v1/curation/status/{trace_id}/ - Check curation status
- GET /api/v1/curation/health/ - Health check
- CRUD /api/v1/curation/config/ - Tenant configuration
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from media_curation.views import (
    CurationViewSet,
    CurationHealthView,
    TenantConfigViewSet,
)

# Create router for ViewSet
# Note: Register more specific routes first, then general ones
router = DefaultRouter()
router.register(r"config", TenantConfigViewSet, basename="tenant-config")
router.register(r"", CurationViewSet, basename="curation")

urlpatterns = [
    # Health check (public endpoint)
    path("health/", CurationHealthView.as_view(), name="curation-health"),
    # ViewSet routes
    path("", include(router.urls)),
]
