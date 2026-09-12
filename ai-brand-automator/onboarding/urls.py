from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    CompanyViewSet,
    BrandAssetViewSet,
    OnboardingProgressViewSet,
    pipeline_status_webhook,
    pipeline_batch_status_webhook,
)
from .internal_views import InternalAssetRegisterView, InternalAssetOCRUpdateView

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
    # Internal service-to-service endpoints (X-Service-Token auth)
    path(
        "internal/assets/register/",
        InternalAssetRegisterView.as_view(),
        name="internal-asset-register",
    ),
    path(
        "internal/assets/<int:pk>/ocr/",
        InternalAssetOCRUpdateView.as_view(),
        name="internal-asset-ocr-update",
    ),
] + router.urls
