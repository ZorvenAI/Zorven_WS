"""Session CRUD and the state-machine API (Design §10.2, §9.4).

The Onboarding Interface drives a session through these endpoints without
being trusted to know the transition rules, so every status change is
validated here rather than in the client.
"""

from __future__ import annotations

from django.db import IntegrityError
from rest_framework import status as http
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.onboarding import errors
from apps.onboarding.models import OnboardingSession, tenant_scope_q
from apps.onboarding.serializers import OnboardingSessionSerializer
from apps.onboarding.services.session_state import InvalidTransition, transition
from tenants.permissions import (
    IsTenantEditor,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)


class OnboardingSessionViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """``/api/v1/onboarding/sessions/``.

    Per §15, Owner, Admin and Editor may create and patch; Viewer may read.
    ``IsTenantEditor`` already admits the roles above it, matching how the
    rest of the platform expresses the same matrix.
    """

    serializer_class = OnboardingSessionSerializer
    queryset = OnboardingSession.objects.all()

    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantEditor],
        "update": [IsAuthenticated, IsTenantEditor],
        "partial_update": [IsAuthenticated, IsTenantEditor],
        "destroy": [IsAuthenticated, IsTenantEditor],
    }

    def get_queryset(self):
        """Tenant-scoped, which is also what makes a cross-tenant id 404.

        AC-3 wants 404 rather than 403 for another tenant's session, so that
        the API does not confirm the row exists. Filtering the queryset gets
        that for free from ``get_object()`` — no special case, and it matches
        the behaviour of the platform's other viewsets.
        """
        queryset = OnboardingSession.objects.select_related(
            "company", "questionnaire", "created_by"
        )
        # Never read request.tenant directly — the fleet's defensive pattern.
        tenant = getattr(self.request, "tenant", None)
        queryset = queryset.filter(tenant_scope_q(tenant))

        company = self.request.query_params.get("company")
        if company:
            queryset = queryset.filter(company_id=company)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            tenant=getattr(self.request, "tenant", None),
            created_by=user if user and user.is_authenticated else None,
        )

    def create(self, request, *args, **kwargs):
        """Surface the one-active-session rule as 409 rather than a 500.

        The constraint is the B-01 partial unique index, so the check is the
        database's; this only translates it. Re-checking in Python first
        would be a race — two requests can both pass the check and only one
        can pass the index.
        """
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {
                    "code": errors.LIVE_SESSION_ACTIVE,
                    "detail": (
                        "This company already has an active onboarding "
                        "session. Complete or archive it first."
                    ),
                },
                status=http.HTTP_409_CONFLICT,
            )

    def update(self, request, *args, **kwargs):
        """PATCH/PUT, with any status change routed through §9.4.

        The status is applied *before* the serializer runs so that a refused
        transition rejects the whole request — a partial update that saved
        the other fields and dropped the status would leave the caller with
        a 409 and a half-applied change.
        """
        session = self.get_object()
        target = request.data.get("status")

        if target and target != session.status:
            try:
                transition(session, target)
            except InvalidTransition as exc:
                return Response(
                    {
                        "code": exc.code,
                        "detail": str(exc),
                        "current_state": exc.current,
                        "legal_next_states": exc.allowed,
                    },
                    status=http.HTTP_409_CONFLICT,
                )

        return super().update(request, *args, **kwargs)
