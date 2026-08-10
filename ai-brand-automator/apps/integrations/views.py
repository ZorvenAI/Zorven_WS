"""Connect, disconnect and inspect a tenant's calendar connection (D-02).

Admin and Owner only, per §15 and AC-1. Everything here is Django-side; §19
forbids the agent holding calendar credentials, so none of these endpoints
have a service-token counterpart.
"""

from __future__ import annotations

import logging
import secrets as secrets_module

from django.utils import timezone
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.integrations import google_calendar
from apps.integrations.models import CalendarConnection, ConnectionStatus
from tenants.permissions import IsTenantAdmin

logger = logging.getLogger(__name__)

#: Where the consent flow returns. Kept in the session between /connect/ and
#: /callback/ so a forged callback cannot choose its own redirect.
STATE_SESSION_KEY = "google_calendar_oauth_state"


def _audit(event: str, *, request, connection: CalendarConnection, **extra) -> None:
    """Record a connection lifecycle event.

    AC-2: "an audit event records the connection with the acting user,
    carrying no token material". The signature makes that easy to honour and
    hard to breach — it takes the connection and reads only non-secret fields
    off it, so there is no parameter a token could arrive through.
    """
    logger.info(
        "calendar_connection_%s",
        event,
        extra={
            "event": f"calendar_connection_{event}",
            "tenant_id": connection.tenant_id,
            "provider": connection.provider,
            "secret_path": connection.secret_path,
            "acting_user_id": getattr(request.user, "id", None),
            "status": connection.status,
            **extra,
        },
    )


def _tenant_of(request):
    return getattr(request, "tenant", None)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def connect(request):
    """Start the OAuth flow. Returns the URL the browser should visit.

    A URL rather than a redirect, because the caller is the SPA: a 302 from an
    XHR is followed by the browser without the operator ever seeing Google's
    consent screen, which is both broken and alarming.
    """
    if not google_calendar.is_configured():
        return Response(
            {
                "error": "google_oauth_not_configured",
                "detail": (
                    "This deployment has no Google OAuth credentials. The "
                    "in-app calendar works without them."
                ),
            },
            status=http.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # A random state, held server-side. Without it a third party can hand an
    # operator a callback URL carrying *their* authorisation code and connect
    # the attacker's calendar to this tenant.
    state = secrets_module.token_urlsafe(32)
    request.session[STATE_SESSION_KEY] = state

    redirect_uri = request.build_absolute_uri(
        "/api/v1/integrations/google-calendar/callback/"
    )
    return Response(
        {
            "authorisation_url": google_calendar.authorisation_url(
                redirect_uri=redirect_uri, state=state
            ),
            "scope": google_calendar.SCOPE,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def callback(request):
    """Complete the exchange and store the encrypted refresh token."""
    tenant = _tenant_of(request)
    if tenant is None:
        return Response(
            {"error": "a tenant is required to connect a calendar"},
            status=http.HTTP_400_BAD_REQUEST,
        )

    expected = request.session.pop(STATE_SESSION_KEY, None)
    supplied = str(request.data.get("state") or "")
    if not expected or not secrets_module.compare_digest(supplied, expected):
        # Constant-time, and a single message for both halves: telling a
        # caller whether the state was missing or merely wrong is a hint.
        return Response(
            {"error": "invalid_state", "detail": "Start the connection again."},
            status=http.HTTP_400_BAD_REQUEST,
        )

    code = str(request.data.get("code") or "").strip()
    if not code:
        return Response({"error": "code is required"}, status=http.HTTP_400_BAD_REQUEST)

    redirect_uri = request.build_absolute_uri(
        "/api/v1/integrations/google-calendar/callback/"
    )
    try:
        tokens = google_calendar.exchange_code(code=code, redirect_uri=redirect_uri)
    except google_calendar.OAuthError as exc:
        return Response(
            {"error": "oauth_failed", "detail": exc.reason},
            status=http.HTTP_400_BAD_REQUEST,
        )

    connection, _ = CalendarConnection.objects.get_or_create(
        tenant=tenant, provider="google_calendar"
    )
    connection.refresh_token = tokens["refresh_token"]
    connection.scope = tokens.get("scope", google_calendar.SCOPE)
    connection.status = ConnectionStatus.CONNECTED
    connection.last_error = ""
    connection.connected_by = request.user
    connection.last_refreshed_at = timezone.now()
    connection.save()

    _audit("connected", request=request, connection=connection)
    return Response(_describe(connection), status=http.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def disconnect(request):
    """Revoke upstream, then delete the secret (AC-3).

    In that order. Deleting first and failing to revoke would leave a live
    grant on the operator's Google account that nothing in this system knows
    about — unrevokable from here, and invisible to them.
    """
    tenant = _tenant_of(request)
    connection = (
        CalendarConnection.objects.filter(tenant=tenant, provider="google_calendar")
        .exclude(status=ConnectionStatus.DISCONNECTED)
        .first()
    )
    if connection is None:
        return Response(
            {"error": "no calendar is connected"}, status=http.HTTP_404_NOT_FOUND
        )

    token = connection.refresh_token
    if token:
        try:
            google_calendar.revoke(refresh_token=token)
        except google_calendar.OAuthError as exc:
            # Not swallowed. If the operator is told "disconnected" while the
            # grant is still live at Google, the one thing AC-3 promises has
            # not happened.
            return Response(
                {"error": "revocation_failed", "detail": exc.reason},
                status=http.HTTP_502_BAD_GATEWAY,
            )

    connection.refresh_token = None
    connection.status = ConnectionStatus.DISCONNECTED
    connection.last_error = ""
    connection.save()

    _audit("disconnected", request=request, connection=connection)
    return Response(_describe(connection))


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def connection_status(request):
    """What the calendar pane needs for AC-4's reconnect prompt."""
    connection = CalendarConnection.objects.filter(
        tenant=_tenant_of(request), provider="google_calendar"
    ).first()
    if connection is None:
        return Response(
            {
                "connected": False,
                "status": ConnectionStatus.DISCONNECTED,
                "configured": google_calendar.is_configured(),
            }
        )
    return Response(_describe(connection))


def _describe(connection: CalendarConnection) -> dict:
    """The public shape of a connection.

    Built by hand rather than by a ModelSerializer. A serializer over this
    model would expose whatever fields it was given, and the one field that
    must never leave the process is a column on it — an explicit dict cannot
    grow a token by someone adding it to `fields`.
    """
    return {
        "connected": connection.is_usable,
        "status": connection.status,
        "provider": connection.provider,
        "scope": connection.scope,
        "google_account_email": connection.google_account_email,
        "connected_at": connection.connected_at,
        "last_refreshed_at": connection.last_refreshed_at,
        # AC-4: specific, so the pane can say what went wrong rather than
        # going quietly stale.
        "needs_reconnect": connection.status == ConnectionStatus.NEEDS_RECONNECT,
        "last_error": connection.last_error,
        "configured": google_calendar.is_configured(),
    }
