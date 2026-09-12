"""Shared fixtures for e2e tests (N-01 AC-1).

Extracted from the ``test_ws_handshake.py`` pattern: a local HTTP server
standing in for Django, per-test unique company IDs, and a TestClient
with ``FakeSTTAdapter`` injected.
"""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.providers.stt import FakeSTTAdapter
from app.services.backend_client import BackendClient

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "two_speaker_2min.jsonl"
FIXTURE_45MIN_PATH = (
    Path(__file__).parent.parent / "fixtures" / "two_speaker_45min.jsonl"
)


@pytest.fixture
def django_stub():
    """A local stand-in for Django's live-precheck endpoint."""
    state = {
        "status": 200,
        "body": {
            "approved": True,
            "consent": {"present": True, "active": True, "consent_id": "c-1"},
        },
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(
                {"path": self.path, "tenant": self.headers.get("X-Tenant-ID")}
            )
            body = dict(state["body"])
            req_tenant = self.headers.get("X-Tenant-ID") or "t-1"
            body.setdefault(
                "auth",
                {
                    "valid": True,
                    "tenant_id": req_tenant,
                    "company_id": state.get("company_id", "c-1"),
                    "user_id": "u-1",
                    "role": "editor",
                    "valid_until": "2099-01-01T00:00:00+00:00",
                },
            )
            body.setdefault(
                "consent", {"present": True, "active": True, "consent_id": "c-1"}
            )
            if state.get("questions"):
                body.setdefault("questions", state["questions"])
            payload = json.dumps(body).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield state
    finally:
        t = threading.Thread(target=server.shutdown, daemon=True)
        t.start()
        t.join(timeout=5)
        server.server_close()


@pytest.fixture
def live_company(request):
    """A company id unique to each test, avoiding lock contention."""
    return f"c-{hashlib.md5(request.node.name.encode()).hexdigest()[:8]}"


@pytest.fixture
def e2e_client(app_with_live_redis, django_stub, live_company):
    """TestClient with FakeSTTAdapter injected and fast polling."""
    with TestClient(app_with_live_redis) as tc:
        app_with_live_redis.state.stt = FakeSTTAdapter(FIXTURE_PATH)
        app_with_live_redis.state.backend = BackendClient(django_stub["url"], "tok")
        app_with_live_redis.state.live_poll_s = 0.05
        django_stub["company_id"] = live_company
        yield tc


@pytest.fixture
def e2e_client_45min(app_with_live_redis, django_stub, live_company):
    """TestClient with FakeSTTAdapter loaded with the 45-minute fixture."""
    with TestClient(app_with_live_redis) as tc:
        app_with_live_redis.state.stt = FakeSTTAdapter(FIXTURE_45MIN_PATH)
        app_with_live_redis.state.backend = BackendClient(django_stub["url"], "tok")
        app_with_live_redis.state.live_poll_s = 0.05
        django_stub["company_id"] = live_company
        yield tc
