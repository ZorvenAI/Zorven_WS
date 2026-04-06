"""URL configuration for the optimization app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CampaignRegistryViewSet,
    optimization_tick_callback,
    register_campaign,
)

router = DefaultRouter()
router.register(r"campaigns", CampaignRegistryViewSet, basename="campaign-registry")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "callback/tick-result/",
        optimization_tick_callback,
        name="optimization-tick-callback",
    ),
    path(
        "register/",
        register_campaign,
        name="optimization-register-campaign",
    ),
]
