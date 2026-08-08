"""Session CRUD and the state-machine API (Design §10.2, §9.4).

The Onboarding Interface drives a session through these endpoints without
being trusted to know the transition rules, so every status change is
validated here rather than in the client.
"""

from __future__ import annotations

import json

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import mixins
from rest_framework import status as http
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.onboarding import errors
from apps.onboarding.field_map import label_for, page_for
from apps.onboarding.events import (
    ACTION_CONFIRM,
    ACTION_EDIT,
    emit_provenance_reviewed,
)
from apps.onboarding.models import (
    FieldClassification,
    FieldProvenance,
    OnboardingSession,
    ProvenanceStatus,
    tenant_scope_q,
)
from apps.onboarding.serializers import (
    FieldProvenanceSerializer,
    OnboardingSessionSerializer,
    ProvenanceEditSerializer,
)
from apps.onboarding.services.session_state import InvalidTransition, transition
from apps.onboarding.text import levenshtein
from tenants.permissions import (
    IsTenantAdmin,
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

    @db_transaction.atomic
    def update(self, request, *args, **kwargs):
        """PATCH/PUT, with any status change routed through §9.4.

        The transition is checked and applied **in memory** (``save=False``)
        and only reaches the database through the serializer's save, so the
        request is all-or-nothing in both directions:

        - a refused transition returns 409 having written nothing;
        - a legal transition followed by a serializer error returns 400,
          also having written nothing.

        An earlier version saved the transition first and then called
        ``super().update()``. That looked right — it rejected the whole
        request on a bad transition — but got the other order wrong: a legal
        status change with an invalid field alongside it returned 400 with
        the status already committed. Caught in review on PR #546, and
        ``test_a_serializer_error_does_not_leave_the_status_changed`` now
        holds it.

        ``super().update()`` cannot be reused here because it re-fetches the
        row through ``get_object()`` and would discard the in-memory change.
        """
        partial = kwargs.pop("partial", False)
        session = self.get_object()
        target = request.data.get("status")

        if target and target != session.status:
            try:
                transition(session, target, save=False)
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

        serializer = self.get_serializer(session, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def provenance(self, request, pk=None):
        """``GET /sessions/{id}/provenance/`` — grouped by wizard page (AC-1).

        Grouped rather than flat because the review page shows the extraction
        in the order the operator would have typed it. A field with no page
        lands in ``unmapped`` rather than being dropped, so a field added
        without updating field_map.py looks wrong in review instead of
        silently disappearing from it.
        """
        session = self.get_object()
        rows = (
            FieldProvenance.objects.filter(session=session)
            .select_related("session")
            .order_by("model_name", "field_name")
        )

        buckets: dict[object, list] = {}
        for row in rows:
            buckets.setdefault(page_for(row.field_name), []).append(row)

        groups = []
        for page in sorted(
            buckets, key=lambda p: (p is None, p if p is not None else 0)
        ):
            groups.append(
                {
                    "page": page,
                    "label": label_for(page),
                    "fields": FieldProvenanceSerializer(buckets[page], many=True).data,
                }
            )

        return Response({"session": session.pk, "groups": groups})


class FieldProvenanceViewSet(
    RoleBasedPermissionMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """``/api/v1/onboarding/provenance/{id}/`` — review actions (§10.2).

    Confirm and edit are POST actions rather than PATCH because they are not
    field updates: each one records a human decision, sets the reviewer and
    timestamp, and emits EVT-109. A PATCH surface would invite a client to
    write ``status`` or ``extracted_value`` directly.
    """

    serializer_class = FieldProvenanceSerializer
    queryset = FieldProvenance.objects.all()

    role_permissions = {
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "confirm": [IsAuthenticated, IsTenantEditor],
        "edit": [IsAuthenticated, IsTenantEditor],
    }

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        return FieldProvenance.objects.select_related("session").filter(
            tenant_scope_q(tenant)
        )

    def _refuse_key_without_admin(self, row):
        """§15 and §10.2: "Admin (KEY) / Editor (SECONDARY)".

        An Editor may run extraction but may not sign off an identity-defining
        field — §3 puts it plainly, "KEY fields require explicit ADMIN
        confirmation before final submit". Returns a response to send, or None
        to proceed.
        """
        if row.classification != FieldClassification.KEY:
            return None
        if IsTenantAdmin().has_permission(self.request, self):
            return None
        return Response(
            {
                "code": errors.ROLE_DENIED,
                "detail": (
                    "A KEY field requires Admin confirmation. Editors may "
                    "review SECONDARY fields only."
                ),
                "classification": row.classification,
            },
            status=http.HTTP_403_FORBIDDEN,
        )

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """Accept the extracted value as-is.

        Idempotent: confirming an already-CONFIRMED row returns 200 and emits
        nothing. A second event would inflate the confirm-without-edit rate
        that §17.3 reads as extraction quality.
        """
        row = self.get_object()

        refusal = self._refuse_key_without_admin(row)
        if refusal is not None:
            return refusal

        if row.status == ProvenanceStatus.CONFIRMED:
            return Response(self.get_serializer(row).data)

        row.status = ProvenanceStatus.CONFIRMED
        row.reviewed_by = request.user if request.user.is_authenticated else None
        row.reviewed_at = timezone.now()
        row.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

        emit_provenance_reviewed(
            tenant_id=row.tenant_id,
            session_id=row.session_id,
            field_name=row.field_name,
            action=ACTION_CONFIRM,
            edit_distance=0,
            classification=row.classification,
        )
        return Response(self.get_serializer(row).data)

    @action(detail=True, methods=["post"])
    def edit(self, request, pk=None):
        """Record a human value alongside — never over — the extracted one."""
        row = self.get_object()

        refusal = self._refuse_key_without_admin(row)
        if refusal is not None:
            return refusal

        payload = ProvenanceEditSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        final_value = payload.validated_data["final_value"]

        distance = levenshtein(_as_text(row.extracted_value), _as_text(final_value))

        row.final_value = final_value
        row.status = ProvenanceStatus.EDITED
        row.reviewed_by = request.user if request.user.is_authenticated else None
        row.reviewed_at = timezone.now()
        # extracted_value is absent from update_fields on purpose: L-02 needs
        # the agent's original proposal to compare against.
        row.save(
            update_fields=[
                "final_value",
                "status",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        emit_provenance_reviewed(
            tenant_id=row.tenant_id,
            session_id=row.session_id,
            field_name=row.field_name,
            action=ACTION_EDIT,
            edit_distance=distance,
            classification=row.classification,
        )
        return Response(self.get_serializer(row).data)


def _as_text(value) -> str:
    """A value's string form, for edit distance only.

    JSON values are canonicalised with sorted keys so that a reordering is
    not mistaken for an edit. The result is used to compute one integer and
    then discarded — it never reaches the event.
    """
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)
