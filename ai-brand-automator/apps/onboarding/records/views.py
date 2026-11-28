"""HTTP surface for meeting records.

Explicit POST actions rather than a PATCH surface, for the same reason the
questionnaire and provenance endpoints are: issuing and voiding record human
decisions, not field updates.

Reading is open to any tenant member; preparing, issuing and voiding need an
editor. PDFs are returned directly rather than through a storage link — a
record that is not yet fully signed is rendered on request and never stored.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponse
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.onboarding.models import MeetingRecording, OnboardingSession, tenant_scope_q
from apps.onboarding.records import completion, lifecycle, readiness, signing
from apps.onboarding.records.clauses import CONSENT_VERSION, consent_text
from apps.onboarding.records.lifecycle import RecordError
from apps.onboarding.records.models import (
    MeetingRecord,
    RecordEventType,
    RecordStatus,
    SignatoryParty,
    SigningMethod,
)
from apps.onboarding.records.pdf import (
    build_binder_pdf,
    build_record_pdf,
)
from apps.onboarding.records.presentation import (
    acknowledgements_owed,
    events_of as _events,
    signatory_private,
    snapshot_of as _snapshot_of,
    view_of as _view,
)
from tenants.permissions import IsTenantEditor, IsTenantViewer

READ = [IsAuthenticated, IsTenantViewer]
WRITE = [IsAuthenticated, IsTenantEditor]

# ── Scoping ──────────────────────────────────────────────────────────


def _scope(queryset, request):
    tenant = getattr(request, "tenant", None)
    if tenant:
        return queryset.filter(tenant_scope_q(tenant))
    return queryset.filter(tenant__isnull=True)


def _session_or_404(request, pk) -> OnboardingSession:
    session = (
        _scope(OnboardingSession.objects.select_related("company", "tenant"), request)
        .filter(pk=pk)
        .first()
    )
    if session is None:
        raise Http404
    return session


def _record_or_404(request, pk) -> MeetingRecord:
    record = (
        _scope(
            MeetingRecord.objects.select_related(
                "recording", "session", "session__company", "tenant", "supersedes"
            ),
            request,
        )
        .filter(pk=pk)
        .first()
    )
    if record is None:
        raise Http404
    return record


def _valid_ip(value: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return None


def _client_ip(request) -> str | None:
    """The caller's address, for the audit trail.

    ``X-Forwarded-For`` is a list each proxy appends to, and everything to the
    left of what our own proxies added was supplied by the caller. Reading
    the first entry — the usual shortcut — would let anyone write an address
    of their choosing into a record's audit trail.

    So this counts in from the right. ``RECORDS_TRUSTED_PROXY_COUNT`` is how
    many proxies in front of this service append to the header: 1 behind
    Cloud Run's front end or Kong (the default), 0 when the service is
    reached directly, in which case the header is ignored altogether. With
    fewer entries than trusted proxies the header cannot be what it claims,
    and the socket address is used instead.

    Anything that is not an IP address is stored as nothing rather than
    passed on: the column would reject it and fail the request.
    """
    trusted = int(getattr(settings, "RECORDS_TRUSTED_PROXY_COUNT", 1))
    hops = [
        hop.strip()
        for hop in (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")
        if hop.strip()
    ]
    if trusted > 0 and len(hops) >= trusted:
        return _valid_ip(hops[-trusted])
    return _valid_ip(request.META.get("REMOTE_ADDR"))


def _refusal(error: RecordError) -> Response:
    conflict = {
        "record_exists",
        "record_completed",
        "supersede_required",
        "not_draft",
        "not_ready",
        "is_draft",
        "is_terminal",
        "not_supersedable",
        "already_superseded",
        "not_open",
        "already_acted",
        "content_mismatch",
    }
    return Response(
        {"error": error.code, "detail": error.message, **error.extra},
        status=(
            http.HTTP_409_CONFLICT
            if error.code in conflict
            else http.HTTP_400_BAD_REQUEST
        ),
    )


# ── Shaping ──────────────────────────────────────────────────────────


def _summary(record: MeetingRecord) -> dict[str, Any]:
    return {
        "id": record.pk,
        "record_number": record.record_number,
        "version": record.version,
        "status": record.status,
        "recording_id": record.recording_id,
        "session_id": record.session_id,
        "content_hash": record.content_hash,
        "clause_version": record.clause_version,
        "issued_at": record.issued_at,
        "voided_at": record.voided_at,
        "void_reason": record.void_reason,
        "supersedes": record.supersedes_id,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "completed_at": record.completed_at,
        "pdf_hash": record.pdf_hash,
    }


def _signatory_of(record: MeetingRecord, user) -> int | None:
    """Which signatory the viewer is, by their account's email address."""
    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return None
    for s in record.signatories.all():
        if s.party == SignatoryParty.AGENCY and s.email.lower() == email:
            return s.pk
    return None


def _detail(record: MeetingRecord, user=None) -> dict[str, Any]:
    snapshot = _snapshot_of(record)
    body = _summary(record)
    body["you"] = _signatory_of(record, user)
    body["consent"] = {"version": CONSENT_VERSION, "text": consent_text()}
    body["document"] = snapshot
    body["events"] = _events(record)
    body["signatories"] = [
        signatory_private(s, snapshot) for s in record.signatories.all()
    ]
    body["remarks_to_acknowledge"] = acknowledgements_owed(record)
    body["readiness"] = (
        [item.as_dict() for item in readiness.check_readiness(record, snapshot)]
        if record.status == RecordStatus.DRAFT
        else []
    )
    return body


def _pdf_response(data: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


# ── Endpoints ────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes(READ)
def session_records(request, pk):
    """``GET sessions/<pk>/records/`` — every meeting, with its record if any.

    One row per recording, oldest first, so the interface can offer "Prepare"
    for a meeting that has no record yet. ``record`` is the latest version;
    ``history`` lists the earlier ones.
    """
    session = _session_or_404(request, pk)
    records: dict[int, list[MeetingRecord]] = {}
    for record in MeetingRecord.objects.filter(session=session).order_by("version"):
        records.setdefault(record.recording_id, []).append(record)

    meetings = []
    for recording in MeetingRecording.objects.filter(session=session).order_by(
        "created_at"
    ):
        versions = records.get(recording.pk, [])
        meetings.append(
            {
                "recording_id": recording.pk,
                "started_at": recording.started_at,
                "has_content": lifecycle.has_content(recording),
                "record": _summary(versions[-1]) if versions else None,
                "history": [_summary(r) for r in versions[:-1]],
            }
        )
    return Response({"meetings": meetings})


@api_view(["POST"])
@permission_classes(WRITE)
def create_record(request, pk):
    """``POST recordings/<pk>/records/`` — open a draft for one meeting."""
    recording = (
        _scope(MeetingRecording.objects.select_related("session"), request)
        .filter(pk=pk)
        .first()
    )
    if recording is None:
        raise Http404
    try:
        with transaction.atomic():
            record = lifecycle.create_draft(
                recording, user=request.user, ip_address=_client_ip(request)
            )
            # A starting point, not a decision: the preparer and the client's
            # authorised signatory, both editable until issue.
            signing.set_signatories(
                record, signing.default_signatories(record, request.user)
            )
    except RecordError as error:
        return _refusal(error)
    return Response(
        _detail(_record_or_404(request, record.pk), request.user), status=201
    )


@api_view(["GET"])
@permission_classes(READ)
def record_detail(request, pk):
    """``GET records/<pk>/`` — the record, its content, events and readiness."""
    return Response(_detail(_record_or_404(request, pk), request.user))


@api_view(["POST"])
@permission_classes(WRITE)
def discard_record(request, pk):
    """``POST records/<pk>/discard/`` — remove a draft that was never issued."""
    record = _record_or_404(request, pk)
    try:
        lifecycle.discard_draft(record)
    except RecordError as error:
        return _refusal(error)
    return Response(status=http.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes(WRITE)
def issue_record(request, pk):
    """``POST records/<pk>/issue/`` — freeze the content. Cannot be undone."""
    record = _record_or_404(request, pk)
    try:
        lifecycle.issue(
            record,
            user=request.user,
            ip_address=_client_ip(request),
            acknowledge_incomplete=request.data.get("acknowledge_incomplete") is True,
        )
    except RecordError as error:
        return _refusal(error)
    # ``issue`` has committed by now, so a link is never emailed for a record
    # whose issue rolled back.
    completion.send_signing_requests(pk)
    return Response(_detail(_record_or_404(request, pk), request.user))


@api_view(["PUT"])
@permission_classes(WRITE)
def record_signatories(request, pk):
    """``PUT records/<pk>/signatories/`` — replace a draft's signatories."""
    record = _record_or_404(request, pk)
    try:
        signing.set_signatories(record, request.data.get("signatories"))
    except RecordError as error:
        return _refusal(error)
    return Response(_detail(_record_or_404(request, pk), request.user))


@api_view(["POST"])
@permission_classes(WRITE)
def remind_record(request, pk):
    """``POST records/<pk>/remind/`` — resend to everyone yet to sign.

    Each reminder carries a new link and retires the previous one, so this is
    also how a link sent to the wrong place is cancelled.
    """
    record = _record_or_404(request, pk)
    if record.status not in signing.OPEN_STATUSES:
        return _refusal(
            RecordError(
                "not_open",
                f"{record.record_number} is not awaiting signatures.",
            )
        )
    lifecycle.log_event(
        record,
        RecordEventType.REMINDED,
        user=request.user,
        ip_address=_client_ip(request),
    )
    sent = completion.send_signing_requests(pk, reminder=True)
    return Response(
        {"sent": sent, **_detail(_record_or_404(request, pk), request.user)}
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantViewer])
def sign_record(request, pk):
    """``POST records/<pk>/sign/`` — sign as yourself, while logged in.

    Being logged in stands in for the emailed code. Which signatory you are
    is decided by your account's email address, never by the request: nobody
    can sign in another person's place by naming them.
    """
    record = _record_or_404(request, pk)
    email = (request.user.email or "").strip().lower()
    # Only the agency's own signatories sign from the workspace. A client
    # signatory always proves their address with the emailed code, even if
    # someone holds a workspace account under the same email.
    signatory = (
        record.signatories.filter(
            email__iexact=email, party=SignatoryParty.AGENCY
        ).first()
        if email
        else None
    )
    if signatory is None:
        return Response(
            {
                "error": "not_a_signatory",
                "detail": "You are not named as a signatory on this record.",
            },
            status=http.HTTP_403_FORBIDDEN,
        )
    action = str(request.data.get("action") or "")
    try:
        signed = signing.act(
            signatory,
            action,
            method=SigningMethod.ACCOUNT,
            content_hash=str(request.data.get("content_hash") or ""),
            typed_name=str(request.data.get("typed_name") or ""),
            consent=request.data.get("consent") is True,
            remarks=str(request.data.get("remarks") or ""),
            reason=str(request.data.get("reason") or ""),
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
            user=request.user,
        )
    except RecordError as error:
        return _refusal(error)
    completion.after_action(signed, action)
    return Response(_detail(_record_or_404(request, pk), request.user))


@api_view(["POST"])
@permission_classes(WRITE)
def void_record(request, pk):
    """``POST records/<pk>/void/`` — withdraw an issued record, with a reason."""
    record = _record_or_404(request, pk)
    try:
        lifecycle.void(
            record,
            reason=str(request.data.get("reason") or ""),
            user=request.user,
            ip_address=_client_ip(request),
        )
    except RecordError as error:
        return _refusal(error)
    return Response(_detail(_record_or_404(request, pk), request.user))


@api_view(["POST"])
@permission_classes(WRITE)
def supersede_record(request, pk):
    """``POST records/<pk>/supersede/`` — open the next version as a draft."""
    record = _record_or_404(request, pk)
    try:
        with transaction.atomic():
            successor = lifecycle.supersede(
                record, user=request.user, ip_address=_client_ip(request)
            )
            # Carried over as they were named, not as they signed: the new
            # version is a new document and everyone signs it afresh.
            signing.set_signatories(
                successor,
                [
                    {
                        "party": s.party,
                        "name": s.name,
                        "title": s.title,
                        "email": s.email,
                        "required": s.required,
                    }
                    for s in record.signatories.all()
                ],
            )
    except RecordError as error:
        return _refusal(error)
    return Response(
        _detail(_record_or_404(request, successor.pk), request.user), status=201
    )


@api_view(["GET"])
@permission_classes(READ)
def record_pdf(request, pk):
    """``GET records/<pk>/pdf/`` — the record as a PDF."""
    record = _record_or_404(request, pk)
    data = build_record_pdf(_view(record))
    lifecycle.log_event(
        record,
        RecordEventType.DOWNLOADED,
        user=request.user,
        ip_address=_client_ip(request),
        kind="record",
    )
    return _pdf_response(data, f"{record.record_number}.pdf")


@api_view(["GET"])
@permission_classes(READ)
def session_binder(request, pk):
    """``GET sessions/<pk>/binder/`` — every meeting's record in one PDF.

    Each meeting contributes its latest version unless that version is void
    with nothing newer, in which case it is still shown, marked void: a binder
    that silently dropped a withdrawn record would misstate the history.
    """
    session = _session_or_404(request, pk)
    latest: dict[int, MeetingRecord] = {}
    for record in (
        MeetingRecord.objects.filter(session=session)
        .select_related(
            "recording", "session", "session__company", "tenant", "supersedes"
        )
        .order_by("version")
    ):
        latest[record.recording_id] = record

    ordered = sorted(latest.values(), key=lambda r: r.recording.created_at)
    data = build_binder_pdf(
        [_view(record) for record in ordered],
        agency_name=getattr(session.tenant, "name", "") or "",
        client_name=(
            getattr(session.company, "legal_name", None)
            or getattr(session.company, "name", "")
            or ""
        ),
    )
    for record in ordered:
        lifecycle.log_event(
            record,
            RecordEventType.DOWNLOADED,
            user=request.user,
            ip_address=_client_ip(request),
            kind="binder",
        )
    return _pdf_response(data, f"meeting-records-session-{session.pk}.pdf")
