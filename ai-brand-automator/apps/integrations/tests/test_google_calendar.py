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

            if self.path.endswith("/revoke"):
                code, body = state["revoke_status"], {}
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


def complete_connection(api_client, google):
    """Walk the real flow: ask for a URL, then post back the code."""
    started = api_client.get(CONNECT)
    assert started.status_code == 200, started.content
    state = started.json()["authorisation_url"].split("state=")[1].split("&")[0]
    return api_client.post(
        CALLBACK, {"code": "auth-code", "state": state}, format="json"
    )


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
    assert api_client.post(CALLBACK, {"code": "x"}, format="json").status_code == 403
    assert api_client.post(DISCONNECT, format="json").status_code == 403
    assert not CalendarConnection.objects.exists()


def test_an_admin_can_connect(api_client, tenant, google, admin):
    """The control. A permission that refused everyone would pass the test
    above while making the feature impossible."""
    response = complete_connection(api_client, google)

    assert response.status_code == 201, response.content
    assert response.json()["connected"] is True


# ── AC-2 · encrypted, per tenant, never in the clear ─────────────────


def test_the_refresh_token_is_encrypted_at_rest(api_client, tenant, google, admin):
    complete_connection(api_client, google)

    connection = CalendarConnection.objects.get()
    assert connection.refresh_token == "refresh-abc"
    # The column holds ciphertext. Reading it raw must not yield the secret —
    # that is the whole of "encrypted at rest".
    assert connection._refresh_token != "refresh-abc"
    assert "refresh-abc" not in connection._refresh_token


def test_the_secret_path_follows_the_design(api_client, tenant, google, admin):
    """§19 names it secrets/<tenant_id>/google_calendar."""
    complete_connection(api_client, google)

    connection = CalendarConnection.objects.get()
    assert connection.secret_path == f"secrets/{tenant.pk}/google_calendar"


def test_the_response_never_carries_the_token(api_client, tenant, google, admin):
    body = complete_connection(api_client, google).json()

    assert "refresh-abc" not in json.dumps(body)
    assert "refresh_token" not in body


def test_a_missing_refresh_token_is_refused(api_client, tenant, google, admin):
    """Google omits it on a repeat authorisation. Storing the connection
    anyway leaves something that looks connected and dies at the first
    expiry with nothing to refresh from."""
    google["token_response"] = {"access_token": "access-only"}

    response = complete_connection(api_client, google)

    assert response.status_code == 400
    assert "offline access" in response.json()["detail"]
    assert not CalendarConnection.objects.exists()


def test_the_narrow_scope_is_requested(api_client, tenant, google, admin):
    """calendar.events, not calendar — a full grant would let this app delete
    an operator's own appointments."""
    url = api_client.get(CONNECT).json()["authorisation_url"]

    assert "calendar.events" in url
    assert "auth%2Fcalendar&" not in url


def test_a_forged_callback_is_refused(api_client, tenant, google, admin):
    """Without the state check, a third party can hand an operator a callback
    carrying *their* code and attach the attacker's calendar to this tenant."""
    api_client.get(CONNECT)

    response = api_client.post(
        CALLBACK, {"code": "auth-code", "state": "not-the-state"}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_state"
    assert not CalendarConnection.objects.exists()


# ── AC-3 · disconnect actually revokes ───────────────────────────────


def test_disconnect_revokes_upstream(api_client, tenant, google, admin):
    """The card's named case, asserted at the wire.

    Checking the row went to DISCONNECTED would pass whether or not Google
    was ever told. The only proof is that the refresh token reached the revoke
    endpoint, which is why the stub records its requests.
    """
    complete_connection(api_client, google)
    google["requests"].clear()

    response = api_client.post(DISCONNECT, format="json")

    assert response.status_code == 200, response.content
    revocations = [r for r in google["requests"] if r["path"].endswith("/revoke")]
    assert len(revocations) == 1
    assert revocations[0]["form"]["token"] == "refresh-abc"


def test_disconnect_clears_the_stored_secret(api_client, tenant, google, admin):
    complete_connection(api_client, google)

    api_client.post(DISCONNECT, format="json")

    connection = CalendarConnection.objects.get()
    assert connection.status == ConnectionStatus.DISCONNECTED
    assert connection._refresh_token == ""
    assert connection.refresh_token is None


def test_a_failed_revocation_does_not_report_success(api_client, tenant, google, admin):
    """Telling the operator "disconnected" while the grant is still live at
    Google is the one thing AC-3 rules out."""
    complete_connection(api_client, google)
    google["revoke_status"] = 500

    response = api_client.post(DISCONNECT, format="json")

    assert response.status_code == 502
    connection = CalendarConnection.objects.get()
    assert connection.status == ConnectionStatus.CONNECTED
    assert connection.refresh_token == "refresh-abc"


def test_an_already_forgotten_grant_disconnects_cleanly(
    api_client, tenant, google, admin
):
    """Google answers 400 for a grant it no longer knows. The goal state is
    "no live grant", and it is already reached — refusing here would strand
    the operator with a connection they cannot remove."""
    complete_connection(api_client, google)
    google["revoke_status"] = 400

    response = api_client.post(DISCONNECT, format="json")

    assert response.status_code == 200
    assert CalendarConnection.objects.get().status == ConnectionStatus.DISCONNECTED


# ── AC-4 · a stale grant is legible ──────────────────────────────────


def test_a_revoked_grant_is_marked_for_reconnect(api_client, tenant, google, admin):
    """The scheduled refresh is what makes AC-4 possible: the connection is
    already marked before the operator tries to use it."""
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, google)
    google["token_status"] = 400
    google["token_response"] = {"error": "invalid_grant"}

    result = refresh_calendar_tokens()

    assert result == {"refreshed": 0, "needs_reconnect": 1}
    connection = CalendarConnection.objects.get()
    assert connection.status == ConnectionStatus.NEEDS_RECONNECT
    assert "invalid_grant" in connection.last_error


def test_the_status_endpoint_tells_the_pane_to_reconnect(
    api_client, tenant, google, admin
):
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, google)
    google["token_status"] = 400
    google["token_response"] = {"error": "invalid_grant"}
    refresh_calendar_tokens()

    body = api_client.get(STATUS).json()

    assert body["needs_reconnect"] is True
    assert body["connected"] is False
    assert "invalid_grant" in body["last_error"]


def test_a_healthy_grant_stays_connected(api_client, tenant, google, admin):
    """The control. A refresh task that marked everything would pass the tests
    above and disconnect every working calendar on its first run."""
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, google)

    result = refresh_calendar_tokens()

    assert result == {"refreshed": 1, "needs_reconnect": 0}
    assert CalendarConnection.objects.get().status == ConnectionStatus.CONNECTED


def test_one_tenants_dead_grant_does_not_stop_the_sweep(
    api_client, tenant, google, admin
):
    """A task that died on the first failure would leave every connection it
    never reached looking healthy."""
    from apps.integrations.tasks import refresh_calendar_tokens

    complete_connection(api_client, google)
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
