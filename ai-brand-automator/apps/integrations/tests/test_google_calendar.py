"""D-02 · connecting and disconnecting Google Calendar.

The card names `test_editor_cannot_connect` and `test_disconnect_revokes_upstream`.

No mocks. `GOOGLE_OAUTH_BASE` points the real OAuth code at a local HTTP
server, so `exchange_code`, `revoke` and `_post` all execute — including their
error handling, which is where the interesting behaviour is. Mocking those
functions would test everything except them, which is the mistake #564 made
and #566 was written to avoid.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.integrations.models import CalendarConnection, ConnectionStatus
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

CONNECT = "/api/v1/integrations/google-calendar/connect/"
CALLBACK = "/api/v1/integrations/google-calendar/callback/"
DISCONNECT = "/api/v1/integrations/google-calendar/disconnect/"
STATUS = "/api/v1/integrations/google-calendar/status/"


@pytest.fixture
def google():
    """A local stand-in for Google's token and revoke endpoints.

    Records what it was sent, so a test can assert the *refresh token* reached
    the revoke endpoint — which is the whole of AC-3 and cannot be checked
    from this side of the wire any other way.
    """
    state = {
        "token_response": {
            "refresh_token": "refresh-abc",
            "access_token": "access-xyz",
            "scope": "https://www.googleapis.com/auth/calendar.events",
        },
        "token_status": 200,
        "revoke_status": 200,
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            from urllib.parse import parse_qs

            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode()
            state["requests"].append(
                {"path": self.path, "form": {k: v[0] for k, v in parse_qs(raw).items()}}
            )

            form = state["requests"][-1]["form"]
            if self.path.endswith("/revoke"):
                code, body = state["revoke_status"], {}
            elif not (form.get("client_id") and form.get("client_secret")):
                # What Google actually answers when the caller has no
                # credentials. Returning a token here regardless would make a
                # worker that never received the client secret look healthy in
                # tests while condemning every calendar in production.
                code, body = 401, {"error": "invalid_client"}
            else:
                code, body = state["token_status"], state["token_response"]

            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    previous = {
        key: os.environ.get(key)
        for key in (
            "GOOGLE_OAUTH_BASE",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
        )
    }
    os.environ["GOOGLE_OAUTH_BASE"] = f"http://127.0.0.1:{server.server_address[1]}"
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    try:
        yield state
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        server.shutdown()
        server.server_close()


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="D02 Co", schema_name="d02_cal")


def member(api_client, tenant, role, username):
    user = User.objects.create_user(username, f"{username}@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=role)
    api_client.force_authenticate(user=user)
    return user


@pytest.fixture
def admin(api_client, tenant):
    return member(api_client, tenant, Membership.Role.ADMIN, "d02_admin")


@pytest.fixture
def browser():
    """Google's redirect, as it actually arrives.

    A *separate* client from the SPA's, carrying no JWT and no cookie from
    /connect/. This distinction is the whole point: Django's test client keeps
    a session across requests, so driving the callback with `api_client` would
    let a session-held state match and make a flow that cannot complete in
    production look correct in CI. That is exactly how the first cut of this
    endpoint passed its tests.
    """
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


def start_connection(api_client) -> str:
    """Ask for the consent URL and return the state Google will hand back."""
    started = api_client.get(CONNECT)
    assert started.status_code == 200, started.content
    return started.json()["authorization_url"].split("state=")[1].split("&")[0]


def complete_connection(api_client, browser, google=None):
    """Walk the real round trip: the SPA starts it, the browser finishes it."""
    return browser.get(
        CALLBACK, {"code": "auth-code", "state": start_connection(api_client)}
    )


def query_of(response) -> dict:
    """The parameters the operator is sent back to the pane with."""
    from urllib.parse import parse_qs, urlparse

    return {k: v[0] for k, v in parse_qs(urlparse(response["Location"]).query).items()}


# ── AC-1 · only Admins and Owners ────────────────────────────────────


@pytest.mark.parametrize("role", ["editor", "viewer"])
def test_editor_cannot_connect(api_client, tenant, google, role):
    """The card's named case, for both roles below Admin."""
    member(
        api_client,
        tenant,
        Membership.Role.EDITOR if role == "editor" else Membership.Role.VIEWER,
        f"d02_{role}",
    )

    assert api_client.get(CONNECT).status_code == 403
    assert api_client.post(DISCONNECT, format="json").status_code == 403
    assert not CalendarConnection.objects.exists()


def test_the_open_callback_is_not_a_way_round_the_role_check(
    api_client, browser, tenant, google
):
    """The callback has to be unauthenticated, so the role check has to hold
    somewhere else — it holds at the state.

    An Editor cannot obtain a state, and the callback will not act without
    one. Making the callback public would otherwise hand every role the
    ability an Admin has.
    """
    member(api_client, tenant, Membership.Role.EDITOR, "d02_sneak")

    assert api_client.get(CONNECT).status_code == 403
    # No state to be had, so nothing an Editor can put in front of the callback.
    response = browser.get(CALLBACK, {"code": "auth-code", "state": str(uuid.uuid4())})

    assert query_of(response)["error"] == "invalid_state"
    assert not CalendarConnection.objects.exists()


def test_an_admin_can_connect(api_client, browser, tenant, google, admin):
    """The control. A permission that refused everyone would pass the test
    above while making the feature impossible."""
    response = complete_connection(api_client, browser, google)

    assert response.status_code == 302, response.content
    assert query_of(response) == {"connected": "1"}
    assert CalendarConnection.objects.get().is_usable is True


def test_the_callback_completes_without_authentication(
    api_client, browser, tenant, google, admin
):
    """The finding this rework exists for.

    Google's redirect is a top-level browser navigation carrying no
    Authorization header and no cookie of ours. When the callback required
    both, the round trip could not complete at all — the operator landed on a
    405 and no calendar was ever connected.
    """
    state = start_connection(api_client)

    # Not merely unauthenticated: a client that has never seen this server.
    assert "HTTP_AUTHORIZATION" not in browser.defaults
    response = browser.get(CALLBACK, {"code": "auth-code", "state": state})

    assert response.status_code == 302
    assert query_of(response) == {"connected": "1"}
    assert CalendarConnection.objects.get().tenant_id == tenant.pk


def test_the_connection_belongs_to_the_tenant_that_started_it(
    api_client, browser, tenant, google, admin
):
    """The callback arrives on the backend's own host, where
    DefaultTenantMiddleware resolves `request.tenant` to the *public* tenant.
    Reading the tenant from the request there would file every connected
    calendar under the wrong owner. It is read off the state row instead.
    """
    complete_connection(api_client, browser, google)

    connection = CalendarConnection.objects.get()
    assert connection.tenant_id == tenant.pk
    assert connection.connected_by_id == admin.pk


def test_a_state_cannot_be_replayed(api_client, browser, tenant, google, admin):
    """One authorisation, one connection. A reusable state would let anyone
    who saw the redirect URL — in a browser history, a proxy log, a referrer —
    drive the callback again."""
    state = start_connection(api_client)
    assert query_of(browser.get(CALLBACK, {"code": "auth-code", "state": state})) == {
        "connected": "1"
    }

    replayed = browser.get(CALLBACK, {"code": "auth-code", "state": state})

    assert query_of(replayed)["error"] == "invalid_state"


def test_a_state_is_burned_even_when_the_exchange_fails(
    api_client, browser, tenant, google, admin
):
    """Otherwise a failed exchange leaves a live state behind, and the
    single-use guarantee above holds only on the happy path."""
    google["token_status"] = 400
    google["token_response"] = {"error": "invalid_grant"}
    state = start_connection(api_client)
    browser.get(CALLBACK, {"code": "auth-code", "state": state})

    google["token_status"] = 200
    google["token_response"] = {"refresh_token": "refresh-abc"}
    retried = browser.get(CALLBACK, {"code": "auth-code", "state": state})

    assert query_of(retried)["error"] == "invalid_state"
    assert not CalendarConnection.objects.exists()


def test_an_expired_state_is_refused(api_client, browser, tenant, google, admin):
    """Ten minutes, per OAuthState. A state that never expired would stay
    usable for as long as the row survived."""
    from datetime import timedelta

    from django.utils import timezone as tz

    from automation.models import OAuthState

    state = start_connection(api_client)
    OAuthState.objects.filter(state=state).update(
        created_at=tz.now() - timedelta(minutes=11)
    )

    response = browser.get(CALLBACK, {"code": "auth-code", "state": state})

    assert query_of(response)["error"] == "state_expired"
    assert not CalendarConnection.objects.exists()


def test_a_declined_consent_returns_the_operator_to_the_pane(
    api_client, browser, tenant, google, admin
):
    """Google sends `?error=access_denied` when the operator says no. Landing
    them on raw JSON at an API host would be the wrong end to a deliberate
    choice."""
    state = start_connection(api_client)

    response = browser.get(CALLBACK, {"error": "access_denied", "state": state})

    assert response["Location"].startswith("http://localhost:3000/onboarding?")
    assert query_of(response)["error"] == "access_denied"
    assert not CalendarConnection.objects.exists()


def test_the_start_url_uses_the_conventional_key(api_client, tenant, google, admin):
    """Every other OAuth start in this codebase answers `authorization_url`
    (automation/views.py). One endpoint spelling it differently is a contract
    an integrator has to memorise."""
    body = api_client.get(CONNECT).json()

    assert "authorization_url" in body
    assert "authorisation_url" not in body


# ── AC-2 · encrypted, per tenant, never in the clear ─────────────────


def test_the_refresh_token_is_encrypted_at_rest(
    api_client, browser, tenant, google, admin
):
    complete_connection(api_client, browser, google)

    connection = CalendarConnection.objects.get()
    assert connection.refresh_token == "refresh-abc"
    # The column holds ciphertext. Reading it raw must not yield the secret —
    # that is the whole of "encrypted at rest".
    assert connection._refresh_token != "refresh-abc"
    assert "refresh-abc" not in connection._refresh_token


def test_the_secret_path_follows_the_design(api_client, browser, tenant, google, admin):
    """§19 names it secrets/<tenant_id>/google_calendar."""
    complete_connection(api_client, browser, google)

    connection = CalendarConnection.objects.get()
    assert connection.secret_path == f"secrets/{tenant.pk}/google_calendar"


def test_the_redirect_never_carries_the_token(
    api_client, browser, tenant, google, admin
):
    """A redirect URL is worse than a response body: it lands in browser
    history, referrer headers and every proxy log on the way."""
    response = complete_connection(api_client, browser, google)

    assert "refresh-abc" not in response["Location"]
    assert "access-xyz" not in response["Location"]


def test_the_status_endpoint_never_carries_the_token(
    api_client, browser, tenant, google, admin
):
    complete_connection(api_client, browser, google)

    body = api_client.get(STATUS).json()

    assert "refresh-abc" not in json.dumps(body)
    assert "refresh_token" not in body


def test_a_missing_refresh_token_is_refused(api_client, browser, tenant, google, admin):
    """Google omits it on a repeat authorisation. Storing the connection
    anyway leaves something that looks connected and dies at the first
    expiry with nothing to refresh from."""
    google["token_response"] = {"access_token": "access-only"}

    response = complete_connection(api_client, browser, google)

    returned = query_of(response)
    assert returned["error"] == "oauth_failed"
    assert "offline access" in returned["detail"]
    assert not CalendarConnection.objects.exists()


def test_the_narrow_scope_is_requested(api_client, browser, tenant, google, admin):
    """calendar.events, not calendar — a full grant would let this app delete
    an operator's own appointments."""
    url = api_client.get(CONNECT).json()["authorization_url"]

    assert "calendar.events" in url
    assert "auth%2Fcalendar&" not in url


def test_a_forged_callback_is_refused(api_client, browser, tenant, google, admin):
    """Without the state check, a third party can hand an operator a callback
    carrying *their* code and attach the attacker's calendar to this tenant."""
    start_connection(api_client)

    response = browser.get(CALLBACK, {"code": "auth-code", "state": "not-the-state"})

    assert query_of(response)["error"] == "invalid_state"
    assert not CalendarConnection.objects.exists()


# ── AC-3 · disconnect actually revokes ───────────────────────────────


def test_disconnect_revokes_upstream(api_client, browser, tenant, google, admin):
    """The card's named case, asserted at the wire.

    Checking the row went to DISCONNECTED would pass whether or not Google
    was ever told. The only proof is that the refresh token reached the revoke
    endpoint, which is why the stub records its requests.
    """
    complete_connection(api_client, browser, google)
    google["requests"].clear()

    response = api_client.post(DISCONNECT, format="json")

    assert response.status_code == 200, response.content
    revocations = [r for r in google["requests"] if r["path"].endswith("/revoke")]
    assert len(revocations) == 1
    assert revocations[0]["form"]["token"] == "refresh-abc"


def test_disconnect_clears_the_stored_secret(
    api_client, browser, tenant, google, admin
):
    complete_connection(api_client, browser, google)

    api_client.post(DISCONNECT, format="json")

    connection = CalendarConnection.objects.get()
    assert connection.status == ConnectionStatus.DISCONNECTED
    assert connection._refresh_token == ""
    assert connection.refresh_token is None


def test_a_failed_revocation_does_not_report_success(
    api_client, browser, tenant, google, admin
):
    """Telling the operator "disconnected" while the grant is still live at
    Google is the one thing AC-3 rules out."""
    complete_connection(api_client, browser, google)
    google["revoke_status"] = 500

    response = api_client.post(DISCONNECT, format="json")

    assert response.status_code == 502
    connection = CalendarConnection.objects.get()
    assert connection.status == ConnectionStatus.CONNECTED
    assert connection.refresh_token == "refresh-abc"


def test_an_already_forgotten_grant_disconnects_cleanly(
    api_client, browser, tenant, google, admin
):
    """Google answers 400 for a grant it no longer knows. The goal state is
    "no live grant", and it is already reached — refusing here would strand
    the operator with a connection they cannot remove."""
    complete_connection(api_client, browser, google)
    google["revoke_status"] = 400

    response = api_client.post(DISCONNECT, format="json")

    assert response.status_code == 200
    assert CalendarConnection.objects.get().status == ConnectionStatus.DISCONNECTED


# ── AC-4 · a stale grant is legible ──────────────────────────────────


def test_a_revoked_grant_is_marked_for_reconnect(
    api_client, browser, tenant, google, admin
):
    """The scheduled refresh is what makes AC-4 possible: the connection is
    already marked before the operator tries to use it."""
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, browser, google)
    google["token_status"] = 400
    google["token_response"] = {"error": "invalid_grant"}

    result = refresh_calendar_tokens()

    assert result == {"refreshed": 0, "needs_reconnect": 1}
    connection = CalendarConnection.objects.get()
    assert connection.status == ConnectionStatus.NEEDS_RECONNECT
    assert "invalid_grant" in connection.last_error


def test_the_status_endpoint_tells_the_pane_to_reconnect(
    api_client, browser, tenant, google, admin
):
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, browser, google)
    google["token_status"] = 400
    google["token_response"] = {"error": "invalid_grant"}
    refresh_calendar_tokens()

    body = api_client.get(STATUS).json()

    assert body["needs_reconnect"] is True
    assert body["connected"] is False
    assert "invalid_grant" in body["last_error"]


def test_a_healthy_grant_stays_connected(api_client, browser, tenant, google, admin):
    """The control. A refresh task that marked everything would pass the tests
    above and disconnect every working calendar on its first run."""
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, browser, google)

    result = refresh_calendar_tokens()

    assert result == {"refreshed": 1, "needs_reconnect": 0}
    assert CalendarConnection.objects.get().status == ConnectionStatus.CONNECTED


def test_one_tenants_dead_grant_does_not_stop_the_sweep(
    api_client, browser, tenant, google, admin
):
    """A task that died on the first failure would leave every connection it
    never reached looking healthy."""
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, browser, google)
    other = Tenant.objects.create(name="Other", schema_name="d02_other")
    second = CalendarConnection.objects.create(tenant=other)
    second.refresh_token = "refresh-def"
    second.save()

    google["token_status"] = 400
    google["token_response"] = {"error": "invalid_grant"}
    result = refresh_calendar_tokens()

    assert result["needs_reconnect"] == 2


# ── Not configured is a supported state ──────────────────────────────


def test_an_unconfigured_deployment_says_so(api_client, tenant, admin, monkeypatch):
    """FR-CAL-01 promises the in-app calendar works with zero external setup,
    so no credentials is an ordinary state rather than an error."""
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)

    response = api_client.get(CONNECT)

    assert response.status_code == 503
    assert response.json()["error"] == "google_oauth_not_configured"


def test_an_unconfigured_worker_condemns_nobody(
    api_client, browser, tenant, google, admin, monkeypatch
):
    """The compose finding, at its sharp end.

    The credentials live only on the backend and the worker. A worker that
    never received them gets `invalid_client` for every connection — this
    deployment being misconfigured, not any operator's grant being revoked —
    and a sweep that took Google at its word would mark every healthy calendar
    in the fleet NEEDS_RECONNECT on the strength of it.
    """
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, browser, google)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)

    result = refresh_calendar_tokens()

    # The consequence first: the calendar is untouched. Asserting the bookkeeping
    # key before this would let a KeyError mask the harm it stands for.
    assert CalendarConnection.objects.get().status == ConnectionStatus.CONNECTED
    assert result == {"refreshed": 0, "needs_reconnect": 0, "skipped": "unconfigured"}
