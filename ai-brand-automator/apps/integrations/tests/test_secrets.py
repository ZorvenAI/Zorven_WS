"""D-02 · token material never leaves the process.

The card names `test_no_token_in_logs_or_events`, and FR-CAL-02 states it
plainly: "Refresh tokens are stored encrypted and never appear in logs or
events".

A test that checked one log line would prove almost nothing — the risk is not
the line someone thought about, it is the one they did not. So these capture
*every* record emitted during a real connect-and-disconnect and search the lot,
including the fields a structured formatter would serialise.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.integrations.models import CalendarConnection
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

CONNECT = "/api/v1/integrations/google-calendar/connect/"
CALLBACK = "/api/v1/integrations/google-calendar/callback/"
DISCONNECT = "/api/v1/integrations/google-calendar/disconnect/"

SECRET = "refresh-token-that-must-never-be-logged"
CLIENT_SECRET = "client-secret-that-must-never-be-logged"


@pytest.fixture
def google():
    state = {"token_status": 200, "revoke_status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            if self.path.endswith("/revoke"):
                code, body = state["revoke_status"], {}
            else:
                code, body = state["token_status"], {
                    "refresh_token": SECRET,
                    "access_token": "access-also-secret",
                }
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
    os.environ["GOOGLE_OAUTH_BASE"] = f"http://127.0.0.1:{server.server_address[1]}"
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = CLIENT_SECRET
    try:
        yield state
    finally:
        for key in (
            "GOOGLE_OAUTH_BASE",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
        ):
            os.environ.pop(key, None)
        server.shutdown()
        server.server_close()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    tenant = Tenant.objects.create(name="D02 Secrets", schema_name="d02_secrets")
    user = User.objects.create_user("d02_sec", "sec@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.ADMIN)
    client.force_authenticate(user=user)
    return client, tenant


class Recorder(logging.Handler):
    """Captures records whole, not just their rendered message.

    A structured formatter serialises `extra` fields into the log line, so a
    token smuggled in through `extra` would reach the log while
    `record.getMessage()` looked clean. Searching the record's `__dict__` is
    what makes this a real check rather than a comforting one.
    """

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

    def haystack(self) -> str:
        parts = []
        for record in self.records:
            parts.append(str(record.getMessage()))
            for key, value in record.__dict__.items():
                if key in {"args", "msg"}:
                    continue
                parts.append(f"{key}={value!r}")
        return "\n".join(parts)


@pytest.fixture
def captured_logs():
    recorder = Recorder()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(recorder)
    root.setLevel(logging.DEBUG)
    try:
        yield recorder
    finally:
        root.removeHandler(recorder)
        root.setLevel(previous_level)


def test_no_token_in_logs_or_events(admin_client, google, captured_logs):
    """The card's named case, over a whole connect-and-disconnect.

    Everything the system logs while handling both halves of the flow is
    searched for the refresh token, the access token and the client secret.
    """
    client, _ = admin_client

    state = (
        client.get(CONNECT).json()["authorisation_url"].split("state=")[1].split("&")[0]
    )
    client.post(CALLBACK, {"code": "auth-code", "state": state}, format="json")
    client.post(DISCONNECT, format="json")

    haystack = captured_logs.haystack()

    assert haystack, "no logs were captured — this test would pass vacuously"
    for secret in (SECRET, "access-also-secret", CLIENT_SECRET):
        assert secret not in haystack, f"{secret!r} reached the logs"


def test_the_audit_records_the_connection_without_the_material(
    admin_client, google, captured_logs
):
    """AC-2's second half: the event names the acting user and the secret's
    path, and carries nothing that could be replayed."""
    client, tenant = admin_client

    state = (
        client.get(CONNECT).json()["authorisation_url"].split("state=")[1].split("&")[0]
    )
    client.post(CALLBACK, {"code": "auth-code", "state": state}, format="json")

    events = [
        r
        for r in captured_logs.records
        if getattr(r, "event", "") == "calendar_connection_connected"
    ]
    assert len(events) == 1, "the connection was not audited"

    event = events[0]
    assert event.tenant_id == tenant.pk
    assert event.acting_user_id is not None
    assert event.secret_path == f"secrets/{tenant.pk}/google_calendar"
    assert SECRET not in json.dumps(
        {k: str(v) for k, v in event.__dict__.items() if k not in {"args", "msg"}}
    )


def test_the_recorder_would_actually_catch_a_leak(captured_logs):
    """The control, and the reason to trust the two tests above.

    A capture that silently missed `extra` fields would let both of them pass
    while a token sat in the logs. This proves the haystack sees what a
    structured formatter would serialise.
    """
    logging.getLogger("probe").warning("nothing here", extra={"token": SECRET})

    assert SECRET in captured_logs.haystack()


def test_the_model_repr_carries_nothing(admin_client, google):
    """__str__ lands in admin pages, shell transcripts and error reports."""
    client, _ = admin_client
    state = (
        client.get(CONNECT).json()["authorisation_url"].split("state=")[1].split("&")[0]
    )
    client.post(CALLBACK, {"code": "auth-code", "state": state}, format="json")

    connection = CalendarConnection.objects.get()

    assert SECRET not in str(connection)
    assert SECRET not in repr(connection)


def test_a_failed_exchange_does_not_log_the_client_secret(
    admin_client, google, captured_logs
):
    """The error path is where secrets usually escape — someone logs the
    request body to work out what went wrong."""
    client, _ = admin_client
    google["token_status"] = 400

    state = (
        client.get(CONNECT).json()["authorisation_url"].split("state=")[1].split("&")[0]
    )
    client.post(CALLBACK, {"code": "auth-code", "state": state}, format="json")

    assert CLIENT_SECRET not in captured_logs.haystack()
