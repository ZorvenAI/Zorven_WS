"""
URL Configuration for RAG Index API.

Defines URL patterns for all RAG Index endpoints using DRF routers.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from rag_index.api.views import (
    HealthViewSet,
    RateLimitViewSet,
    SyncStatusViewSet,
    SyncTriggerViewSet,
)

# Create router and register viewsets
router = DefaultRouter()

# Register viewsets with explicit basenames
router.register(r"sync/status", SyncStatusViewSet, basename="sync-status")
router.register(r"sync", SyncTriggerViewSet, basename="sync")
router.register(r"rate-limit", RateLimitViewSet, basename="rate-limit")

# Health endpoints are handled separately for cleaner URLs
urlpatterns = [
    # Health check endpoints (no auth required)
    path("health/", HealthViewSet.as_view({"get": "health"}), name="health"),
    path("health/ready/", HealthViewSet.as_view({"get": "ready"}), name="health-ready"),
    path("health/live/", HealthViewSet.as_view({"get": "live"}), name="health-live"),
    # Rate limit status endpoint
    path("rate-limit/", RateLimitViewSet.as_view({"get": "status"}), name="rate-limit"),
    # Include router URLs
    path("", include(router.urls)),
]

# The URL patterns will be:
# - GET /health/ - Overall health check
# - GET /health/ready/ - Readiness probe
# - GET /health/live/ - Liveness probe
# - POST /sync/ - Trigger single sync
# - POST /sync/batch/ - Trigger batch sync
# - GET /sync/status/{event_id}/ - Get sync status
# - GET /rate-limit/ - Get rate limit status
