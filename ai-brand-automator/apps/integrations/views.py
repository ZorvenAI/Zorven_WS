"""Connect, disconnect and inspect a tenant's calendar connection (D-02).

Admin and Owner only, per §15 and AC-1. Everything here is Django-side; §19
forbids the agent holding calendar credentials, so none of these endpoints
have a service-token counterpart.
"""

from __future__ import annotations

import logging
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.integrations import google_calendar
from apps.integrations.models import CalendarConnection, ConnectionStatus
from automation.models import OAuthState
from tenants.permissions import IsTenantAdmin, IsTenantViewer

logger = logging.getLogger(__name__)

#: The `platform` discriminator on the shared OAuthState table.
PLATFORM = "google_calendar"

#: Where the operator lands once Google has redirected back to us.
#:
#: The onboarding home, because the dedicated calendar pane does not exist
#: yet — D-02 ships no frontend. Redirecting to a route the SPA has no page
#: for would end a working OAuth round trip on a 404. The pane's story moves
#: this constant and reads the `connected`/`error` parameters already set here.
RETURN_PATH = "/onboarding"


def _audit(event: str, *, acting_user_id, connection: CalendarConnection, **extra):
    """Record a connection lifecycle event.

    AC-2: "an audit event records the connection with the acting user,
    carrying no token material". The signature makes that easy to honour and
    hard to breach — it takes the connection and reads only non-secret fields
    off it, so there is no parameter a token could arrive through.

    The acting user is passed explicitly rather than read off the request: the
    callback is unauthenticated (Google's browser redirect carries no
    credentials of ours), so `request.user` there is anonymous. The operator
    who started the flow is recorded on the state row instead.
    """
    logger.info(
        "calendar_connection_%s",
        event,
        extra={
            "event": f"calendar_connection_{event}",
            "tenant_id": connection.tenant_id,
            "provider": connection.provider,
            "secret_path": connection.secret_path,
            "acting_user_id": acting_user_id,
            "status": connection.status,
            **extra,
        },
    )


def _callback_uri(request) -> str:
    """The redirect_uri, which must be byte-identical in both legs.

    Google compares the value sent at /connect/ with the one sent at exchange
    and rejects the exchange if they differ, so both legs build it here.
    """
    return request.build_absolute_uri("/api/v1/integrations/google-calendar/callback/")


def _return_to(**params) -> HttpResponseRedirect:
    """Send the operator's browser back to the calendar pane.

    The callback is a top-level browser navigation, not an XHR, so its result
    has to be a redirect the operator can see. A JSON body would leave them
    staring at raw output on an API host.
    """
    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    return HttpResponseRedirect(f"{frontend}{RETURN_PATH}?{urlencode(params)}")


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

    tenant = _tenant_of(request)
    if tenant is None:
        # Bound here rather than at the callback: the callback is
        # unauthenticated and arrives on the backend's own host, where
        # DefaultTenantMiddleware would resolve `request.tenant` to the public
        # tenant. A connection made against that would belong to nobody.
        return Response(
            {"error": "a tenant is required to connect a calendar"},
            status=http.HTTP_400_BAD_REQUEST,
        )

    # A random state, held in the database rather than the session. This
    # project authenticates the SPA with JWT and installs no
    # SessionAuthentication, so `request.session` at the callback is a fresh
    # empty session — a session-held state could never match. OAuthState
    # exists for exactly this, and its own docstring says so.
    #
    # Without a state check a third party can hand an operator a callback URL
    # carrying *their* authorisation code and connect the attacker's calendar
    # to this tenant.
    state = str(uuid.uuid4())
    OAuthState.objects.filter(user=request.user, platform=PLATFORM).delete()
    OAuthState.objects.create(
        state=state, user=request.user, platform=PLATFORM, tenant=tenant
    )

    return Response(
        {
            # The conventional spelling, matching every other OAuth start in
            # this codebase (automation/views.py). Nothing consumes this
            # endpoint yet — D-02 ships no frontend pane — so there is no
            # British-spelled key to keep alive alongside it.
            "authorization_url": google_calendar.authorization_url(
                redirect_uri=_callback_uri(request), state=state
            ),
            "scope": google_calendar.SCOPE,
        }
    )


@api_view(["GET"])
# Deliberately open. This is Google's redirect: a top-level browser navigation
# carrying no Authorization header and no cookie of ours. Requiring auth here
# means the round trip can never complete. The `state` row is what
# authenticates it — it is unguessable, single-use, expires in ten minutes,
# and names both the operator and the tenant.
@permission_classes([])
def callback(request):
    """Complete the exchange and store the encrypted refresh token."""
    supplied = request.query_params.get("state") or ""
    error = request.query_params.get("error")

    try:
        oauth_state = OAuthState.objects.select_related("tenant", "user").get(
            state=supplied, platform=PLATFORM, used=False
        )
    except OAuthState.DoesNotExist:
        # Covers forged, replayed and already-consumed states alike, with one
        # message: telling a caller which it was is a hint.
        return _return_to(error="invalid_state")

    if oauth_state.is_expired():
        oauth_state.delete()
        return _return_to(error="state_expired")

    # Burned before the exchange, not after. A code that fails to exchange
    # must not leave a live state behind for a second attempt to reuse.
    oauth_state.used = True
    oauth_state.save(update_fields=["used"])

    tenant, user = oauth_state.tenant, oauth_state.user
    if tenant is None:
        return _return_to(error="no_tenant")

    if error:
        # The operator declined at Google's consent screen, or Google refused.
        return _return_to(error=str(error)[:100])

    code = (request.query_params.get("code") or "").strip()
    if not code:
        return _return_to(error="missing_code")

    try:
        tokens = google_calendar.exchange_code(
            code=code, redirect_uri=_callback_uri(request)
        )
    except google_calendar.OAuthError as exc:
        return _return_to(error="oauth_failed", detail=exc.reason)

    connection, _ = CalendarConnection.objects.get_or_create(
        tenant=tenant, provider=PLATFORM
    )
    connection.refresh_token = tokens["refresh_token"]
    connection.scope = tokens.get("scope", google_calendar.SCOPE)
    connection.status = ConnectionStatus.CONNECTED
    connection.last_error = ""
    connection.connected_by = user
    connection.last_refreshed_at = timezone.now()
    connection.save()

    _audit("connected", acting_user_id=user.pk, connection=connection)
    return _return_to(connected="1")


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
        CalendarConnection.objects.filter(tenant=tenant, provider=PLATFORM)
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

    _audit(
        "disconnected",
        acting_user_id=getattr(request.user, "id", None),
        connection=connection,
    )
    return Response(_describe(connection))


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def connection_status(request):
    """What the calendar pane needs for AC-4's reconnect prompt."""
    connection = CalendarConnection.objects.filter(
        tenant=_tenant_of(request), provider=PLATFORM
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


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantViewer])
def sync_now(request):
    """AC-1's "or immediately on manual refresh".

    A Viewer may trigger this. It writes nothing they could not already see —
    it is a read of Google reflected into rows they have permission to read —
    and the alternative is an operator staring at a pane they know is stale
    because the person who can refresh it is at lunch.

    Runs inline rather than queued. The point of the button is that the answer
    is on screen when it returns; dispatching to Celery would give back a 202
    and leave the pane to poll for a result that arrives no sooner.

    §10.2 names only ``/calendar/events/`` and ``/calendar/connect/``, so this
    path is new. It sits beside the other Google Calendar endpoints rather than
    under ``/onboarding/calendar/`` because D-02 already put ``connect`` here,
    and one integration split across two prefixes is worse than one that does
    not match a document.
    """
    from apps.integrations import sync

    connection = (
        CalendarConnection.objects.filter(
            tenant=_tenant_of(request),
            provider=PLATFORM,
            status=ConnectionStatus.CONNECTED,
        )
        .exclude(_refresh_token="")
        .first()
    )
    if connection is None:
        return Response(
            {"error": "no calendar is connected"}, status=http.HTTP_404_NOT_FOUND
        )

    # Deliberately ignores the backoff. The backoff exists to stop an automated
    # sweep hammering a failing provider; a person pressing refresh is a
    # different thing, and telling them to wait an hour is the behaviour AC-3
    # was written to prevent.
    result = sync.pull_connection(connection)

    # A failed manual sync is a 200 with the failure in it, not a 5xx. AC-3:
    # the failure is "surfaced as a non-blocking notice", and the calendar it
    # was refreshing still works.
    return Response({"result": result, "connection": _describe(connection)})


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
        # AC-3's non-blocking notice. The pane shows these without preventing
        # anything: an in-app calendar that works is the point of the story.
        "last_sync_at": connection.last_sync_at,
        "last_sync_error": connection.last_sync_error,
        "sync_failing": bool(connection.last_sync_error),
    }
