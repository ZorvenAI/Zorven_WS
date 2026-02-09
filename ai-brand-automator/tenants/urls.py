"""
URL configuration for the Tenants app.

Registers DRF router for Tenant and Domain ViewSets.
"""

from rest_framework.routers import DefaultRouter

from .views import DomainViewSet, TenantViewSet

router = DefaultRouter()
# Register DomainViewSet FIRST so /domains/ isn't captured as a tenant pk
router.register(r"domains", DomainViewSet, basename="domain")
router.register(r"", TenantViewSet, basename="tenant")

urlpatterns = router.urls
