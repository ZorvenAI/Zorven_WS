"""
URL routing for Data Ingestion API.

Provides REST endpoints for the data ingestion microservice:
- POST /api/v1/ingestion/ - Submit single event (async)
- POST /api/v1/ingestion/batch/ - Submit batch (async)
- POST /api/v1/ingestion/sync/ - Synchronous processing
- GET /api/v1/ingestion/status/{trace_id}/ - Check status
- GET /api/v1/ingestion/health/ - Health check
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from data_ingestion.views import IngestionViewSet, IngestionHealthView


# Create router for ViewSet (trailing_slash=True to match other apps)
router = DefaultRouter()
router.register(r"", IngestionViewSet, basename="ingestion")


urlpatterns = [
    # Health check (public endpoint)
    path("health/", IngestionHealthView.as_view(), name="ingestion-health"),
    # ViewSet routes (authenticated)
    path("", include(router.urls)),
]
