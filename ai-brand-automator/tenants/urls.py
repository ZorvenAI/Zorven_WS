"""
URL configuration for the Tenants app.

Routes:
  Admin CRUD:
    /api/v1/tenants/              — TenantViewSet  (admin only)
    /api/v1/tenants/domains/      — DomainViewSet   (admin only)
  User-facing workspace:
    /api/v1/tenants/me/           — list user's workspaces
    /api/v1/tenants/create/       — create a new workspace
    /api/v1/tenants/switch/       — switch active workspace (returns JWT)
    /api/v1/tenants/<id>/members/        — list members
    /api/v1/tenants/<id>/members/invite/ — invite by email
    /api/v1/tenants/<id>/members/<mid>/  — update role / remove
    /api/v1/tenants/<id>/delete/         — delete workspace
"""

from django.urls import path

from rest_framework.routers import DefaultRouter

from .views import (
    AcceptInviteView,
    CreateTenantView,
    DeleteTenantView,
    DomainViewSet,
    InviteMemberView,
    MemberDetailView,
    MemberListView,
    MyTenantsView,
    TenantSwitchView,
    TenantViewSet,
)

router = DefaultRouter()
# Register DomainViewSet FIRST so /domains/ isn't captured as a tenant pk
router.register(r"domains", DomainViewSet, basename="domain")
router.register(r"", TenantViewSet, basename="tenant")

urlpatterns = [
    # User-facing workspace endpoints (registered BEFORE router)
    path("me/", MyTenantsView.as_view(), name="tenant-me"),
    path("create/", CreateTenantView.as_view(), name="tenant-create"),
    path("switch/", TenantSwitchView.as_view(), name="tenant-switch"),
    path(
        "invite/accept/",
        AcceptInviteView.as_view(),
        name="tenant-accept-invite",
    ),
    path(
        "<int:tenant_id>/members/",
        MemberListView.as_view(),
        name="tenant-members",
    ),
    path(
        "<int:tenant_id>/members/invite/",
        InviteMemberView.as_view(),
        name="tenant-invite",
    ),
    path(
        "<int:tenant_id>/members/<int:membership_id>/",
        MemberDetailView.as_view(),
        name="tenant-member-detail",
    ),
    path(
        "<int:tenant_id>/delete/",
        DeleteTenantView.as_view(),
        name="tenant-delete",
    ),
] + router.urls
