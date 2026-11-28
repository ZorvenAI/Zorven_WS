"""The signing page's endpoints. No login: the link is the credential.

Four steps, each needing more than the last:

1. ``GET  sign/<token>/``         the link alone — enough to see *that* there
                                  is a record and who it is for, nothing of
                                  its content.
2. ``POST sign/<token>/code/``    emails a one-time code to the signatory.
3. ``POST sign/<token>/verify/``  a correct code opens a short session and
                                  returns the record to read.
4. ``POST sign/<token>/submit/``  that session signs, declines, or
                                  acknowledges remarks.

Every refusal for a bad link is the same 404 with the same body, so a caller
cannot tell an unknown token from an expired one. Throttled per address, and
the code itself is limited per signatory in ``signing.verify_code``.

``authentication_classes = []`` is deliberate, not an oversight: with the
project's default JWT authentication a stale ``Authorization`` header from a
logged-out browser would be rejected with 401 before the token was looked at.
"""

from __future__ import annotations

from typing import Any

from rest_framework import status as http
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.onboarding.records import completion, emails, signing
from apps.onboarding.records.clauses import CONSENT_VERSION, consent_text
from apps.onboarding.records.lifecycle import RecordError, log_event
from apps.onboarding.records.models import (
    RecordEventType,
    RecordSignatory,
    SigningMethod,
)
from apps.onboarding.records.presentation import (
    acknowledgements_owed,
    party_name,
    signatory_public,
)
from apps.onboarding.records.views import _client_ip

SESSION_HEADER = "HTTP_X_SIGNING_SESSION"


class SigningThrottle(AnonRateThrottle):
    """Per address, across all four endpoints."""

    rate = "60/hour"
    scope = "record_signing"


class CodeRequestThrottle(AnonRateThrottle):
    """Sending email is the expensive, abusable step."""

    rate = "10/hour"
    scope = "record_signing_code"


def _not_found() -> Response:
    return Response(
        {
            "error": "link_invalid",
            "detail": "This signing link is not valid or has expired.",
        },
        status=http.HTTP_404_NOT_FOUND,
    )


def _refusal(error: RecordError) -> Response:
    return Response(
        {"error": error.code, "detail": error.message},
        status=http.HTTP_400_BAD_REQUEST,
    )


def _user_agent(request) -> str:
    return request.META.get("HTTP_USER_AGENT", "")[:400]


def _overview(signatory: RecordSignatory) -> dict[str, Any]:
    """What the link alone reveals. No content, no other people's details."""
    record = signatory.record
    snapshot = record.snapshot or {}
    return {
        "record_number": record.record_number,
        "status": record.status,
        "agency": party_name(snapshot, "AGENCY"),
        "client": party_name(snapshot, "CLIENT"),
        "meeting_started_at": snapshot.get("meeting", {}).get("started_at"),
        "expires_at": record.expires_at,
        "signatory": {
            "name": signatory.name,
            "party_name": party_name(snapshot, signatory.party),
            "status": signatory.status,
            "email_hint": signing.mask_email(signatory.email),
        },
    }


def _full(signatory: RecordSignatory) -> dict[str, Any]:
    """The record, for someone who has proved they are the signatory."""
    record = signatory.record
    snapshot = record.snapshot or {}
    owed = acknowledgements_owed(record)
    return {
        **_overview(signatory),
        "content_hash": record.content_hash,
        "document": snapshot,
        "signatories": [
            signatory_public(s, snapshot) for s in record.signatories.all()
        ],
        "consent": {"version": CONSENT_VERSION, "text": consent_text()},
        "can_sign": (
            record.status in signing.OPEN_STATUSES and signatory.status == "PENDING"
        ),
        "remarks_to_acknowledge": owed.get(signatory.pk, []),
    }


def _public(methods, throttles):
    """The decorator stack every endpoint here shares."""

    def wrap(view):
        view = permission_classes([AllowAny])(view)
        view = authentication_classes([])(view)
        view = throttle_classes(throttles)(view)
        return api_view(methods)(view)

    return wrap


@_public(["GET"], [SigningThrottle])
def signing_overview(request, token):
    signatory = signing.resolve_token(token)
    if signatory is None:
        return _not_found()
    log_event(
        signatory.record,
        RecordEventType.VIEWED,
        signatory=signatory,
        ip_address=_client_ip(request),
    )
    return Response(_overview(signatory))


@_public(["POST"], [SigningThrottle, CodeRequestThrottle])
def signing_code(request, token):
    signatory = signing.resolve_token(token)
    if signatory is None:
        return _not_found()
    code = signing.start_code(signatory, ip_address=_client_ip(request))
    if code is None:
        return Response(
            {
                "error": "code_recent",
                "detail": "A code was sent a moment ago. Check your email, or "
                "wait a minute before asking for another.",
            },
            status=http.HTTP_429_TOO_MANY_REQUESTS,
        )
    emails.send_code(signatory.record, signatory, code)
    # The same answer whether or not the email left: this page must not
    # become a way to probe the mail system.
    return Response({"sent_to": signing.mask_email(signatory.email)})


@_public(["POST"], [SigningThrottle])
def signing_verify(request, token):
    signatory = signing.resolve_token(token)
    if signatory is None:
        return _not_found()
    try:
        session = signing.verify_code(
            signatory, request.data.get("code"), ip_address=_client_ip(request)
        )
    except RecordError as error:
        return _refusal(error)
    signatory.refresh_from_db()
    return Response({"session": session, **_full(signatory)})


@_public(["POST"], [SigningThrottle])
def signing_submit(request, token):
    signatory = signing.resolve_token(token)
    if signatory is None:
        return _not_found()
    if not signing.session_is_valid(signatory, request.META.get(SESSION_HEADER, "")):
        return Response(
            {
                "error": "session_expired",
                "detail": "Confirm your email with a new code to continue.",
            },
            status=http.HTTP_401_UNAUTHORIZED,
        )

    action = str(request.data.get("action") or "")
    try:
        record = signing.act(
            signatory,
            action,
            method=SigningMethod.EMAIL_CODE,
            content_hash=str(request.data.get("content_hash") or ""),
            typed_name=str(request.data.get("typed_name") or ""),
            consent=request.data.get("consent") is True,
            remarks=str(request.data.get("remarks") or ""),
            reason=str(request.data.get("reason") or ""),
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except RecordError as error:
        return _refusal(error)

    completion.after_action(record, action)
    signatory.refresh_from_db()
    return Response(_full(signatory))
