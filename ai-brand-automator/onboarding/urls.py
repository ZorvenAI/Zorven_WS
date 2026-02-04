from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    CompanyViewSet,
    BrandAssetViewSet,
    OnboardingProgressViewSet,
    pipeline_status_webhook,
    pipeline_batch_status_webhook,
)

router = DefaultRouter()
router.register(r"companies", CompanyViewSet)
router.register(r"assets", BrandAssetViewSet)
router.register(r"progress", OnboardingProgressViewSet)

urlpatterns = [
    # Pipeline webhook endpoints (for internal services)
    path(
        "webhooks/pipeline-status/",
        pipeline_status_webhook,
        name="pipeline-status-webhook",
    ),
    path(
        "webhooks/pipeline-batch-status/",
        pipeline_batch_status_webhook,
        name="pipeline-batch-status-webhook",
    ),
] + router.urls
