"""Session CRUD and the state-machine API (Design §10.2, §9.4).

The Onboarding Interface drives a session through these endpoints without
being trusted to know the transition rules, so every status change is
validated here rather than in the client.
"""

from __future__ import annotations

import json

from django.db import IntegrityError
from django.db.models import Prefetch
from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import mixins
from rest_framework import status as http
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import hmac

from decouple import config as decouple_config
from django.conf import settings
from django.http import Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from onboarding.models import Company
from tenants.models import Tenant

from apps.onboarding import errors
from apps.onboarding.commands import publish_consent_revoked
from apps.onboarding.field_map import all_mapped_fields, label_for, page_for
from apps.onboarding.events import (
    ACTION_CONFIRM,
    ACTION_EDIT,
    emit_provenance_reviewed,
)
from apps.onboarding.models import (
    ConsentRecord,
    FieldClassification,
    FieldProvenance,
    MeetingRecording,
    OnboardingSession,
    ProvenanceStatus,
    Question,
    QuestionOrigin,
    QuestionStatus,
    Questionnaire,
    QuestionnaireStatus,
    RecordingStatus,
    ResearchBrief,
    SessionStatus,
    WorkflowTarget,
    depth_from,
    tenant_scope_q,
)
from apps.onboarding.serializers import (
    ConsentRecordSerializer,
    FieldProvenanceSerializer,
    MeetingRecordingSerializer,
    OnboardingSessionSerializer,
    ProvenanceEditSerializer,
    QuestionnaireSerializer,
    RecordingStopSerializer,
    ResearchBriefSerializer,
)
from apps.onboarding.services.session_state import InvalidTransition, transition
from apps.onboarding.text import levenshtein, normalise_company_name
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
        # Custom actions are not covered by the entries above: an action name
        # missing from this dict falls back to DEFAULT_PERMISSION_CLASSES,
        # which is bare IsAuthenticated. A user with no tenant membership
        # would then reach tenant_scope_q(None) and read pre-tenant rows.
        "provenance": [IsAuthenticated, IsTenantViewer],
        # §10.2 says Editor+ for consent. The story narrative says "As an
        # Admin", but the endpoint table is the contract, and an Editor
        # running the meeting is who captures consent. This is not the
        # KEY/SECONDARY asymmetry from B-06 — consent is not Admin-gated.
        #
        # Listed explicitly because a custom action missing from this dict
        # falls through to DEFAULT_PERMISSION_CLASSES, which is bare
        # IsAuthenticated. That was the hole review caught on B-06.
        "consent": [IsAuthenticated, IsTenantEditor],
        # GET lists the library and POST opens a recording, so the method
        # decides the role rather than the action name. Editor+ is enforced
        # inside for the write; the entry keeps Viewer out of neither.
        "recordings": [IsAuthenticated, IsTenantViewer],
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
        ).prefetch_related(
            # Without this the serializer's consent field costs one query per
            # session, and the list endpoint uses the same serializer as
            # retrieve — so a page of 20 sessions became 21 queries.
            Prefetch(
                "consent_records",
                queryset=ConsentRecord.objects.filter(revoked_at__isnull=True).order_by(
                    "-granted_at"
                ),
                to_attr="active_consents",
            )
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

    @action(detail=True, methods=["post", "delete"])
    @db_transaction.atomic
    def consent(self, request, pk=None):
        """``POST/DELETE /sessions/{id}/consent/`` — IG-08's prerequisite.

        POST records consent; DELETE revokes it. One action for both because
        they are the same resource, and a client that can find one can find
        the other.
        """
        session = self.get_object()
        if request.method == "DELETE":
            return self._revoke_consent(session)
        return self._grant_consent(request, session)

    def _grant_consent(self, request, session):
        """Record consent, with granted_by and granted_at set server-side.

        FR-REC-01: the timestamp is the server's. A client-chosen consent time
        is the single field an incident would turn on, so the serializer does
        not accept it at all rather than accepting and discarding it.
        """
        # Lock the session before looking for existing consent. Without it
        # the idempotency below is only sequential: two concurrent POSTs can
        # both see none and both create, and there is no unique constraint to
        # catch the second — which would make "was this lawful?" ambiguous in
        # exactly the way one record per conversation exists to prevent.
        (
            self.get_queryset()
            # prefetch_related(None) because this get_queryset() prefetches
            # consent_records for the list endpoint. The locked row is
            # discarded — only the lock matters — so running that prefetch
            # would be a second query inside the critical section, for a
            # result nothing reads.
            .prefetch_related(None)
            .select_for_update(of=("self",))
            .get(pk=session.pk)
        )

        existing = (
            session.consent_records.filter(revoked_at__isnull=True)
            .order_by("-granted_at")
            .first()
        )
        if existing is not None:
            # Idempotent rather than duplicating: two consent rows for one
            # conversation would make "was this lawful?" ambiguous.
            return Response(
                ConsentRecordSerializer(existing).data, status=http.HTTP_200_OK
            )

        payload = ConsentRecordSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        record = payload.save(
            session=session,
            tenant=session.tenant,
            granted_by=request.user if request.user.is_authenticated else None,
        )
        return Response(
            ConsentRecordSerializer(record).data, status=http.HTTP_201_CREATED
        )

    def _revoke_consent(self, session):
        """Revoke, then tell the agent to drop any live socket.

        The order matters: the revocation is committed to PostgreSQL before
        the notification is attempted, because a revocation must succeed even
        if the agent — or the broker — is down.

        Closing the socket itself is F-04's; ``app/api/ws.py`` is still a stub,
        so there is no socket to close today. This publishes the command with
        the shape F-04 will consume.
        """
        record = (
            session.consent_records.filter(revoked_at__isnull=True)
            .order_by("-granted_at")
            .select_for_update()
            .first()
        )
        if record is None:
            # Idempotent: nothing to revoke is not an error, and a 404 here
            # would make a double-click look like a failure.
            return Response(
                {"granted": False, "detail": "No active consent for this session."},
                status=http.HTTP_200_OK,
            )

        record.revoked_at = timezone.now()
        record.save(update_fields=["revoked_at", "updated_at"])

        # on_commit, not inline: this runs inside the action's atomic block,
        # so publishing here would queue the command before the revocation is
        # visible to anyone else — an agent acting on it could read the row
        # and still see consent granted. The docstring above already claimed
        # commit-then-notify; this makes it true.
        db_transaction.on_commit(
            lambda: publish_consent_revoked(
                session_id=session.pk,
                tenant_id=session.tenant_id,
                consent_id=record.pk,
            )
        )
        return Response(ConsentRecordSerializer(record).data, status=http.HTTP_200_OK)

    @action(detail=True, methods=["get", "post"])
    @db_transaction.atomic
    def recordings(self, request, pk=None):
        """``GET/POST /sessions/{id}/recordings/`` — the library and its opener."""
        session = self.get_object()
        if request.method == "POST":
            return self._open_recording(request, session)
        return self._list_recordings(session)

    def _list_recordings(self, session):
        """Newest first, with what the library rail needs (AC-3, FR-LIB-01).

        Read-only for every role including Viewer: a Viewer sees the same
        list, which is what "truthful mid-flight status" means for the person
        watching rather than running the meeting.
        """
        rows = MeetingRecording.objects.filter(session=session).order_by("-started_at")
        return Response(MeetingRecordingSerializer(rows, many=True).data)

    def _open_recording(self, request, session):
        """Refuse without consent, server-side (AC-1, IG-08).

        The gate is here and not only in the UI because IG-08 says so, and
        because a client that can call this endpoint can skip whatever the UI
        would have prevented. No row is created on refusal — a RECORDING row
        for a meeting that never lawfully started would be worse than the
        error.
        """
        if not IsTenantEditor().has_permission(request, self):
            return Response(
                {
                    "code": errors.ROLE_DENIED,
                    "detail": "Opening a recording requires Editor or above.",
                },
                status=http.HTTP_403_FORBIDDEN,
            )

        has_consent = session.consent_records.filter(revoked_at__isnull=True).exists()
        if not has_consent:
            return Response(
                {
                    "code": errors.CONSENT_MISSING,
                    "detail": (
                        "This session has no active consent. Record consent "
                        "before starting a recording."
                    ),
                },
                status=http.HTTP_403_FORBIDDEN,
            )

        recording = MeetingRecording.objects.create(
            session=session,
            tenant=session.tenant,
            status=RecordingStatus.RECORDING,
        )
        return Response(
            MeetingRecordingSerializer(recording).data, status=http.HTTP_201_CREATED
        )


class MeetingRecordingViewSet(
    RoleBasedPermissionMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """``/api/v1/onboarding/recordings/{id}/`` — finalising a cycle (§10.2)."""

    serializer_class = MeetingRecordingSerializer
    queryset = MeetingRecording.objects.all()

    role_permissions = {
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "stop": [IsAuthenticated, IsTenantEditor],
    }

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        return MeetingRecording.objects.select_related("session").filter(
            tenant_scope_q(tenant)
        )

    @action(detail=True, methods=["post"])
    @db_transaction.atomic
    def stop(self, request, pk=None):
        """Finalise exactly the row it opened (AC-2).

        ``UPLOADED``, never ``TRANSCRIBED``: the transcript arrives
        asynchronously from F-05 or the F-06 backfill, and the library has to
        be able to say "transcribing" honestly rather than claiming a
        transcript that does not exist yet.
        """
        recording = self.get_object()
        # Re-locked through get_queryset(), not the global manager: that
        # keeps the tenant filter and select_related("session") applied. The
        # authorisation is not lost today — get_object() above already
        # 404s a cross-tenant id — but a global re-fetch means the lock and
        # the permission check disagree about which rows exist, and it costs
        # an extra session query during serialisation.
        #
        # of=("self",) is required, not stylistic. These querysets
        # select_related nullable FKs, which become LEFT OUTER JOINs, and
        # PostgreSQL refuses "FOR UPDATE cannot be applied to the nullable
        # side of an outer join". Locking only this table sidesteps that
        # while still locking the row that is about to be written — and it
        # is why the original code reached for the global manager.
        recording = (
            self.get_queryset().select_for_update(of=("self",)).get(pk=recording.pk)
        )

        if recording.stopped_at is not None:
            # Idempotent: a second stop must not move the duration. An
            # operator double-clicking should not change what the library
            # reports about their meeting.
            return Response(MeetingRecordingSerializer(recording).data)

        payload = RecordingStopSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        recording.stopped_at = timezone.now()
        recording.status = RecordingStatus.UPLOADED
        # Only when the client reported one. Wall-clock is never computed —
        # see RecordingStopSerializer for why.
        duration = payload.validated_data.get("duration_s")
        fields = ["stopped_at", "status", "updated_at"]
        if duration is not None:
            recording.duration_s = duration
            fields.append("duration_s")

        recording.save(update_fields=fields)
        return Response(MeetingRecordingSerializer(recording).data)


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
    @db_transaction.atomic
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

        # Lock before reading the status. Without this the idempotency below
        # is only *sequentially* idempotent: two concurrent confirms can both
        # read PENDING, both write CONFIRMED and both emit EVT-109, which
        # inflates the confirm-without-edit rate §17.3 reads as quality.
        row = self.get_queryset().select_for_update(of=("self",)).get(pk=row.pk)

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
    @db_transaction.atomic
    def edit(self, request, pk=None):
        """Record a human value alongside — never over — the extracted one."""
        row = self.get_object()

        refusal = self._refuse_key_without_admin(row)
        if refusal is not None:
            return refusal

        row = self.get_queryset().select_for_update(of=("self",)).get(pk=row.pk)

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


class ResearchBriefViewSet(
    RoleBasedPermissionMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """``/api/v1/onboarding/research-briefs/`` — read a stored brief (C-02).

    Read-only by design. The agent writes through
    :func:`upsert_research_brief` behind ``X-Service-Token``; exposing a
    writable surface here would be a second way into the same row with weaker
    guarantees, and the brief is the agent's output rather than something an
    operator authors.

    VIEWER may read. §15 puts SKL-OIA-01 at ALLOW/ALLOW/ALLOW/DENY, but that
    governs *invoking* research — spending money on Tavily calls — not reading
    a brief that already exists. §15's own VIEW_RESULT verdict exists for
    exactly this distinction.
    """

    serializer_class = ResearchBriefSerializer
    queryset = ResearchBrief.objects.all()

    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
    }

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        qs = ResearchBrief.objects.select_related("session").filter(
            tenant_scope_q(tenant)
        )
        name = self.request.query_params.get("company_name")
        if name:
            # Normalised, so a caller searching "Kalyani Roasters Pvt Ltd"
            # finds the brief stored under "kalyani roasters". Matching the
            # raw string would make the lookup depend on how the operator
            # typed it, which is the thing normalisation exists to remove.
            qs = qs.filter(normalised_name=normalise_company_name(name))
        return qs


def _service_tenant(request):
    """The tenant an internal service is acting for, from ``X-Tenant-ID``.

    **Not** ``request.tenant``. Settings put
    ``django_tenants.middleware.default.DefaultTenantMiddleware`` in the chain,
    which falls back to the *public* tenant whenever the host does not match a
    tenant domain — which is always, for an internal service-to-service call
    over the cluster network. Reading ``request.tenant`` on these endpoints
    therefore attributed every agent write to the public tenant regardless of
    which operator it was for.

    That is a cross-tenant defect, not a cosmetic one: ResearchBrief is unique
    on ``(tenant, normalised_name)``, so two tenants researching the same
    business would collide on one public-tenant row — the second overwriting
    the first, and both able to read it.

    ``X-Tenant-ID`` is the fleet's established convention for this; see
    ``automation/internal_views.py`` and the header table in the root
    CLAUDE.md. It is trusted because the caller already proved itself with the
    shared service token. §15's "never read the role from a body" governs a
    *user's* claims; this is a service naming which tenant it acts for.

    Returns ``(tenant, error_response)``. A missing or unknown id is an error
    rather than a fallback, because every fallback available here is wrong:
    the public tenant mixes tenants together, and None makes the row visible
    to all of them.
    """
    raw = request.META.get("HTTP_X_TENANT_ID", "").strip()
    if not raw:
        return None, Response(
            {"error": "X-Tenant-ID header required"},
            status=http.HTTP_400_BAD_REQUEST,
        )
    try:
        tenant = Tenant.objects.filter(pk=raw).first()
    except (ValueError, TypeError):
        # The pk is a BigAutoField, so a non-numeric header raises ValueError
        # out of the queryset rather than returning nothing — a 500 on a
        # request boundary, from a caller sending a malformed header. An id
        # that cannot name a tenant is the same answer as one that names no
        # tenant.
        tenant = None
    if tenant is None:
        return None, Response(
            {"error": f"unknown tenant {raw!r}"},
            status=http.HTTP_400_BAD_REQUEST,
        )
    return tenant, None


@api_view(["POST"])
@permission_classes([AllowAny])
def upsert_research_brief(request):
    """``POST /api/v1/onboarding/research-briefs/upsert/`` — the agent's write.

    ``X-Service-Token`` rather than JWT, matching the fleet: the caller is
    OIA, not a browser, and there is no user session behind it. ``AllowAny``
    is on the DRF permission because the token check below *is* the
    authentication — the same shape as ``orchestration.views.callback_debug``.

    ``hmac.compare_digest`` rather than ``==``: token comparison is the one
    place an early-exit equality check leaks length and prefix through timing.

    **Upsert, not create.** Re-running research for the same business updates
    the row in place. The alternative — accumulating versions — would put a
    second, differently-shaped history alongside Questionnaire's for something
    the backlog never asks to version.

    **A degraded brief never overwrites a good one.** It represents the
    absence of research, so persisting one would let a brief Tavily outage
    erase real findings that cost money to obtain. The agent applies the same
    rule to its Redis cache; enforcing it here too means a future caller
    cannot bypass it.
    """
    token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    expected = getattr(settings, "OIA_SERVICE_TOKEN", "") or decouple_config(
        "OIA_SERVICE_TOKEN", default=""
    )
    if not expected or not hmac.compare_digest(token, expected):
        return Response(
            {"error": "Invalid or missing X-Service-Token"},
            status=http.HTTP_403_FORBIDDEN,
        )

    brief = request.data.get("brief")
    company_name = str(request.data.get("company_name") or "").strip()
    if not isinstance(brief, dict) or not company_name:
        return Response(
            {"error": "company_name and a brief object are required"},
            status=http.HTTP_400_BAD_REQUEST,
        )

    degraded = bool(brief.get("degraded"))
    normalised = normalise_company_name(company_name)

    tenant, error = _service_tenant(request)
    if error is not None:
        return error

    if degraded:
        # Return the existing row if there is one, so the caller sees what is
        # actually stored rather than assuming its degraded copy landed.
        existing = (
            ResearchBrief.objects.filter(tenant_scope_q(tenant))
            .filter(normalised_name=normalised)
            .first()
        )
        return Response(
            {
                "stored": False,
                "reason": "a degraded brief does not overwrite stored research",
                "existing": (
                    ResearchBriefSerializer(existing).data if existing else None
                ),
            },
            status=http.HTTP_200_OK,
        )

    session_id = request.data.get("session_id")
    session = None
    if session_id:
        session = (
            OnboardingSession.objects.filter(tenant_scope_q(tenant))
            .filter(pk=session_id)
            .first()
        )

    with db_transaction.atomic():
        row, created = ResearchBrief.objects.update_or_create(
            tenant=tenant,
            normalised_name=normalised,
            defaults={
                "company_name": company_name,
                "brief": brief,
                "session": session,
                "degraded": False,
                "degraded_reason": "",
                "fact_count": len(brief.get("facts") or []),
                "unknown_count": len(brief.get("open_unknowns") or []),
            },
        )

    return Response(
        {
            "stored": True,
            "created": created,
            "brief": ResearchBriefSerializer(row).data,
        },
        status=http.HTTP_201_CREATED if created else http.HTTP_200_OK,
    )


class QuestionnaireViewSet(
    RoleBasedPermissionMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """``/api/v1/onboarding/questionnaires/`` — read a generated set (C-03).

    Read-only here. The agent writes through :func:`create_questionnaire`
    behind ``X-Service-Token``, and C-04 adds the edit and approval actions as
    explicit POSTs rather than a PATCH surface, for the same reason
    FieldProvenance does: those record human decisions, not field updates.
    """

    serializer_class = QuestionnaireSerializer
    queryset = Questionnaire.objects.all()

    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        # Refinement follows §15's SKL-OIA-01..03 row, which is ALLOW for
        # OWNER, ADMIN and EDITOR and DENY for VIEWER.
        "rewrite": [IsAuthenticated, IsTenantEditor],
        "drop": [IsAuthenticated, IsTenantEditor],
        "reorder": [IsAuthenticated, IsTenantEditor],
        "revise": [IsAuthenticated, IsTenantEditor],
        "clone": [IsAuthenticated, IsTenantEditor],
        # Approval is ADMIN. §15 has no row for it — a gap worth reporting —
        # so this follows the card's "As an Admin" and the precedent of
        # CONFIRM_KEY_FIELD, which is ADMIN-only because it is a decision
        # rather than an edit. Approval gates whether a meeting may start.
        "approve": [IsAuthenticated, IsTenantAdmin],
    }

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        # Prefetch the children: the serializer nests them, and without this
        # a list of N questionnaires is N+1 queries.
        return (
            Questionnaire.objects.select_related("company", "session")
            .prefetch_related("questions")
            .filter(tenant_scope_q(tenant))
        )

    # ── AC-1 · refinement, per question and per set ──────────────────

    def _draft_or_refuse(self, locked: bool = True):
        """The questionnaire, if it is still a DRAFT.

        An APPROVED set is frozen (AC-2). Refusing here rather than letting
        the database trigger fire gives the operator the useful answer —
        "revise it" — instead of an integrity error.
        """
        queryset = self.get_queryset()
        if locked:
            queryset = queryset.select_for_update(of=("self",))
        row = queryset.filter(pk=self.kwargs["pk"]).first()
        if row is None:
            raise Http404
        if row.status != QuestionnaireStatus.DRAFT:
            return None, Response(
                {
                    "error": f"questionnaire {row.pk} is {row.status}",
                    "detail": "Approved sets are frozen. POST to revise/ first.",
                },
                status=http.HTTP_409_CONFLICT,
            )
        return row, None

    @staticmethod
    def _renumber(questionnaire) -> None:
        """Make ordering contiguous from zero.

        AC-1 requires it after *every* operation, which is why this is one
        helper rather than arithmetic repeated in four places — a dropped
        question that left a hole would put the meeting view out of step with
        the numbers the operator refers to out loud.
        """
        for index, question in enumerate(
            questionnaire.questions.order_by("order", "id")
        ):
            if question.order != index:
                question.order = index
                question.save(update_fields=["order"])
        # Queried fresh, not through the related manager: get_queryset()
        # prefetches "questions", so questionnaire.questions.count() answers
        # from the cache populated before this request deleted anything, and
        # the stored count silently drifts from the rows.
        questionnaire.question_count = Question.objects.filter(
            questionnaire=questionnaire
        ).count()
        questionnaire.save(update_fields=["question_count", "updated_at"])

    @action(detail=True, methods=["post"])
    def rewrite(self, request, pk=None):
        """Replace one question's text."""
        with db_transaction.atomic():
            questionnaire, refusal = self._draft_or_refuse()
            if refusal is not None:
                return refusal

            question = questionnaire.questions.filter(
                pk=request.data.get("question_id")
            ).first()
            text = str(request.data.get("text") or "").strip()
            if question is None:
                return Response(
                    {"error": "question_id is not in this questionnaire"},
                    status=http.HTTP_400_BAD_REQUEST,
                )
            if not text:
                return Response(
                    {"error": "text is required"},
                    status=http.HTTP_400_BAD_REQUEST,
                )

            question.text = text
            question.origin = QuestionOrigin.PREPARED
            question.save(update_fields=["text", "origin", "updated_at"])

        return Response(QuestionnaireSerializer(questionnaire).data)

    @action(detail=True, methods=["post"])
    def drop(self, request, pk=None):
        """Remove one question and close the gap."""
        with db_transaction.atomic():
            questionnaire, refusal = self._draft_or_refuse()
            if refusal is not None:
                return refusal

            question = questionnaire.questions.filter(
                pk=request.data.get("question_id")
            ).first()
            if question is None:
                return Response(
                    {"error": "question_id is not in this questionnaire"},
                    status=http.HTTP_400_BAD_REQUEST,
                )
            question.delete()
            self._renumber(questionnaire)

        questionnaire.refresh_from_db()
        return Response(QuestionnaireSerializer(questionnaire).data)

    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        """Set the order from a full list of question ids.

        The list must name every question exactly once. A partial list would
        leave the rest in an order nobody chose, and silently accepting one
        is how an operator ends up reading questions in a sequence they did
        not approve.
        """
        with db_transaction.atomic():
            questionnaire, refusal = self._draft_or_refuse()
            if refusal is not None:
                return refusal

            requested = request.data.get("question_ids")
            existing = list(questionnaire.questions.values_list("id", flat=True))
            if not isinstance(requested, list) or sorted(
                str(i) for i in requested
            ) != sorted(str(i) for i in existing):
                return Response(
                    {
                        "error": "question_ids must list every question exactly once",
                        "expected": existing,
                    },
                    status=http.HTTP_400_BAD_REQUEST,
                )

            for index, question_id in enumerate(requested):
                questionnaire.questions.filter(pk=question_id).update(order=index)
            self._renumber(questionnaire)

        questionnaire.refresh_from_db()
        return Response(QuestionnaireSerializer(questionnaire).data)

    # ── AC-2 · approval freezes a version ────────────────────────────

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Freeze the set and move the session PREPARING → READY."""
        with db_transaction.atomic():
            questionnaire, refusal = self._draft_or_refuse()
            if refusal is not None:
                return refusal

            if not questionnaire.questions.exists():
                return Response(
                    {"error": "an empty questionnaire cannot be approved"},
                    status=http.HTTP_400_BAD_REQUEST,
                )

            questionnaire.status = QuestionnaireStatus.APPROVED
            questionnaire.approved_by = request.user
            questionnaire.approved_at = timezone.now()
            questionnaire.save(
                update_fields=["status", "approved_by", "approved_at", "updated_at"]
            )

            # Through B-04's table, never by assignment — the card's note, and
            # the reason the state machine has no hole. The table already had
            # this edge.
            if questionnaire.session is not None:
                try:
                    transition(questionnaire.session, SessionStatus.READY)
                except InvalidTransition as exc:
                    return Response(
                        {"error": errors.INVALID_TRANSITION, "detail": str(exc)},
                        status=http.HTTP_409_CONFLICT,
                    )

        questionnaire.refresh_from_db()
        return Response(QuestionnaireSerializer(questionnaire).data)

    # ── AC-3 · revision creates a version, never mutates ─────────────

    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        """Open version n+1 as a DRAFT, leaving version n intact.

        ``select_for_update`` on the approved row is the real protection
        against two operators revising at once — not the partial unique
        constraint, which cannot bite while ``company`` is NULL, and NULL is
        the common case because prep precedes onboarding.
        """
        with db_transaction.atomic():
            approved = (
                self.get_queryset()
                .select_for_update(of=("self",))
                .filter(pk=pk)
                .first()
            )
            if approved is None:
                raise Http404
            if approved.status != QuestionnaireStatus.APPROVED:
                return Response(
                    {"error": f"questionnaire {approved.pk} is not APPROVED"},
                    status=http.HTTP_409_CONFLICT,
                )
            if hasattr(approved, "superseded_by"):
                return Response(
                    {
                        "error": "this version has already been revised",
                        "next_version": approved.superseded_by.pk,
                    },
                    status=http.HTTP_409_CONFLICT,
                )

            draft = Questionnaire.objects.create(
                tenant=approved.tenant,
                company=approved.company,
                session=approved.session,
                status=QuestionnaireStatus.DRAFT,
                version=approved.version + 1,
                depth=approved.depth,
                question_count=approved.question_count,
                source_chat_session_id=approved.source_chat_session_id,
                supersedes=approved,
            )
            Question.objects.bulk_create(
                [
                    Question(
                        questionnaire=draft,
                        order=q.order,
                        text=q.text,
                        origin=q.origin,
                        workflow_target=q.workflow_target,
                        target_field=q.target_field,
                        status=QuestionStatus.OPEN,
                    )
                    for q in approved.questions.order_by("order", "id")
                ]
            )

        return Response(
            QuestionnaireSerializer(draft).data, status=http.HTTP_201_CREATED
        )

    # ── D-05 · reuse a template for another company ──────────────────

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """Copy a template questionnaire for another company in this tenant.

        Only from ``is_template``: cloning an arbitrary questionnaire would
        let one company's prepared questions appear under another's name with
        no record of where they came from. The template flag is the operator
        saying "this set is meant to be reused".
        """
        source = self.get_queryset().filter(pk=pk).first()
        if source is None:
            raise Http404
        if not source.is_template:
            return Response(
                {"error": "only a template questionnaire can be cloned"},
                status=http.HTTP_409_CONFLICT,
            )

        tenant = getattr(request, "tenant", None)
        company = Company.objects.filter(
            tenant=tenant, pk=request.data.get("company_id")
        ).first()
        if company is None:
            return Response(
                {"error": "company_id must name a company in this tenant"},
                status=http.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():
            clone = Questionnaire.objects.create(
                tenant=source.tenant,
                company=company,
                status=QuestionnaireStatus.DRAFT,
                version=1,
                depth=source.depth,
                question_count=source.question_count,
            )
            Question.objects.bulk_create(
                [
                    Question(
                        questionnaire=clone,
                        order=q.order,
                        text=q.text,
                        origin=QuestionOrigin.PREPARED,
                        workflow_target=q.workflow_target,
                        target_field=q.target_field,
                        status=QuestionStatus.OPEN,
                    )
                    for q in source.questions.order_by("order", "id")
                ]
            )

        return Response(
            QuestionnaireSerializer(clone).data, status=http.HTTP_201_CREATED
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def create_questionnaire(request):
    """``POST /api/v1/onboarding/questionnaires/generate/`` — the agent's write.

    ``X-Service-Token`` and ``AllowAny`` for the same reason as
    :func:`upsert_research_brief`: the caller is OIA, not a browser, and the
    token check below is the authentication.

    **Validation happens here, not only in the agent.** ``target_field`` is
    checked against B-06's shared vocabulary and WF3 coverage is required,
    because C-03's technical note is explicit that an invented field name
    breaks J-02's join, and FR-PREP-08 says a set covering only the wizard
    pages "fails generation". Enforcing that at the write boundary means a
    second caller — a replay, a fixture, a future story — cannot bypass it.

    Always creates version 1 in DRAFT (AC-4). Regeneration and versioning are
    C-04's, and inventing a version scheme here would prejudge it.
    """
    token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    expected = getattr(settings, "OIA_SERVICE_TOKEN", "")
    if not expected or not hmac.compare_digest(token, expected):
        return Response(
            {"error": "Invalid or missing X-Service-Token"},
            status=http.HTTP_403_FORBIDDEN,
        )

    questions = request.data.get("questions")
    if not isinstance(questions, list) or not questions:
        return Response(
            {"error": "questions must be a non-empty list"},
            status=http.HTTP_400_BAD_REQUEST,
        )

    vocabulary = all_mapped_fields()
    cleaned: list[dict] = []
    invented: list[str] = []

    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            return Response(
                {"error": f"question {index} is not an object"},
                status=http.HTTP_400_BAD_REQUEST,
            )
        text = str(item.get("text") or "").strip()
        if not text:
            return Response(
                {"error": f"question {index} has no text"},
                status=http.HTTP_400_BAD_REQUEST,
            )

        target = str(item.get("workflow_target") or "").strip().upper()
        if target not in WorkflowTarget.values:
            return Response(
                {
                    "error": (
                        f"question {index} has workflow_target {target!r}; "
                        f"expected one of {sorted(WorkflowTarget.values)}"
                    )
                },
                status=http.HTTP_400_BAD_REQUEST,
            )

        field = str(item.get("target_field") or "").strip()
        if field and field not in vocabulary:
            # Dropped to empty rather than rejecting the whole set: one
            # invented name should cost that question its mapping, not cost
            # the operator their questionnaire. Reported so it is visible.
            invented.append(field)
            field = ""

        cleaned.append(
            {
                "text": text,
                "workflow_target": target,
                "target_field": field,
            }
        )

    covered = {q["workflow_target"] for q in cleaned}
    missing = sorted(set(WorkflowTarget.values) - covered)
    if WorkflowTarget.WF3 in missing:
        # FR-PREP-08 names this one specifically: "a set that covers only the
        # five wizard pages fails generation". WF3 is the clause the
        # requirement review added, and it is the one a model silently drops.
        return Response(
            {
                "error": "no WF3 question was generated",
                "detail": (
                    "FR-PREP-08 requires campaign and creative coverage — "
                    "existing ads, business photography, brand assets in use"
                ),
                "missing_workflows": missing,
            },
            status=http.HTTP_400_BAD_REQUEST,
        )

    tenant, error = _service_tenant(request)
    if error is not None:
        return error

    session = None
    session_id = request.data.get("session_id")
    if session_id:
        # Strict, not tenant_scope_q. That predicate admits tenant-less rows,
        # which is correct for a user reading data that predates
        # multi-tenancy and wrong for a service write that was handed an
        # explicit tenant: there is no reason to attach a row from outside it.
        try:
            session = OnboardingSession.objects.filter(
                tenant=tenant, pk=session_id
            ).first()
        except (ValueError, TypeError):
            session = None

    company = None
    company_id = request.data.get("company_id")
    if company_id:
        # Scoped to the header tenant. Unscoped, a service-token caller could
        # attach this questionnaire to another tenant's Company by guessing an
        # id — the same class of cross-tenant defect this PR exists to fix,
        # one field further along.
        try:
            company = Company.objects.filter(tenant=tenant, pk=company_id).first()
        except (ValueError, TypeError):
            company = None
        if company is None:
            return Response(
                {"error": f"company {company_id!r} does not belong to this tenant"},
                status=http.HTTP_400_BAD_REQUEST,
            )
    elif session is not None:
        company = session.company

    with db_transaction.atomic():
        questionnaire = Questionnaire.objects.create(
            tenant=tenant,
            company=company,
            session=session,
            status=QuestionnaireStatus.DRAFT,
            version=1,
            depth=depth_from(request.data.get("depth")),
            question_count=len(cleaned),
            source_chat_session_id=str(request.data.get("chat_session_id") or "")[:64],
        )
        Question.objects.bulk_create(
            [
                Question(
                    # No tenant field: B-01 scopes Question through its
                    # questionnaire rather than repeating the FK, so the
                    # tenant is one row away and cannot disagree with itself.
                    questionnaire=questionnaire,
                    order=index,
                    text=item["text"],
                    origin=QuestionOrigin.PREPARED,
                    workflow_target=item["workflow_target"],
                    target_field=item["target_field"],
                    status=QuestionStatus.OPEN,
                )
                for index, item in enumerate(cleaned)
            ]
        )

    body = QuestionnaireSerializer(questionnaire).data
    if invented:
        body["dropped_target_fields"] = sorted(set(invented))
    if missing:
        body["thin_workflows"] = missing

    return Response(body, status=http.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([AllowAny])
def field_vocabulary(request):
    """``GET /api/v1/onboarding/field-vocabulary/`` — the target_field names.

    C-03's technical note requires target_field to be "drawn from the shared
    apps/onboarding/field_map.py vocabulary introduced in B-06, not invented
    per generation, or J-02 cannot join questions to fields".

    Served rather than duplicated into the agent. The generator needs the list
    *in its prompt* — the write endpoint already drops invented names, but a
    generator working blind would have most of its mappings dropped, which
    satisfies the constraint while losing the joins J-02 needs. One source
    beats two that drift, and this is a list of field names, not a secret.

    Service-token authenticated because the caller is OIA, and tenant-free
    because the vocabulary is a property of the schema rather than of a
    tenant's data.
    """
    token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    expected = getattr(settings, "OIA_SERVICE_TOKEN", "")
    if not expected or not hmac.compare_digest(token, expected):
        return Response(
            {"error": "Invalid or missing X-Service-Token"},
            status=http.HTTP_403_FORBIDDEN,
        )
    return Response({"fields": sorted(all_mapped_fields())}, status=http.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def live_precheck(request, pk):
    """``GET /api/v1/onboarding/sessions/{id}/live-precheck/`` — IG-10's data.

    One call that answers exactly the question the WebSocket gate asks, rather
    than making the agent fetch a session, read its questionnaire id and fetch
    that too. Two reads to decide one thing is two chances to decide it on a
    stale half.

    Returns ``approved`` plus the reason, because C-04 AC-4 requires the close
    to carry "a message naming the missing approval" — a bare false would make
    the agent invent the wording, and it would drift from what Django knows.
    """
    token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    expected = getattr(settings, "OIA_SERVICE_TOKEN", "")
    if not expected or not hmac.compare_digest(token, expected):
        return Response(
            {"error": "Invalid or missing X-Service-Token"},
            status=http.HTTP_403_FORBIDDEN,
        )

    tenant, error = _service_tenant(request)
    if error is not None:
        return error

    try:
        session = (
            OnboardingSession.objects.select_related("questionnaire")
            .filter(tenant=tenant, pk=pk)
            .first()
        )
    except (ValueError, TypeError):
        session = None

    if session is None:
        # 404, not 403 — FR-PREP-06 is explicit that a cross-tenant read must
        # not confirm the row exists.
        return Response({"error": "session not found"}, status=http.HTTP_404_NOT_FOUND)

    questionnaire = session.questionnaire
    if questionnaire is None:
        return Response(
            {
                "approved": False,
                "session_status": session.status,
                "questionnaire_status": None,
                "reason": (
                    "This session has no questionnaire yet. Prepare and approve "
                    "one before starting the meeting."
                ),
            }
        )

    approved = questionnaire.status == QuestionnaireStatus.APPROVED
    return Response(
        {
            "approved": approved,
            "session_status": session.status,
            "questionnaire_status": questionnaire.status,
            "questionnaire_id": questionnaire.pk,
            "reason": (
                ""
                if approved
                else (
                    f"Questionnaire {questionnaire.pk} is "
                    f"{questionnaire.status}. Approve it in preparation before "
                    "starting the meeting."
                )
            ),
        }
    )
