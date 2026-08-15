"""F-04 PR 1 · socket tickets, and the handshake data the agent reads.

A-02 finding 2 is why tickets exist at all: the token travels as `?jwt=`
because browsers cannot set headers on a WebSocket handshake, so it lands in
gateway logs and browser history. A session JWT there is an hour of full API
access sitting in a log file.

The agent never verifies a signature. Django signs HS256 with SECRET_KEY, and
that key also derives the Fernet key protecting every tenant's OAuth refresh
tokens — handing it to the agent to check a signature would put those in the
blast radius of an agent compromise.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.onboarding.live_tickets import USABLE_SECONDS, mint, resolve
from apps.onboarding.models import SessionStatus
from apps.onboarding.tests.factories import make_session
from tenants.models import Membership

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/onboarding/sessions/"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def client_for(user) -> APIClient:
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def editor(public_tenant):
    user = User.objects.create_user("f04_editor", "f04@test.com", "TestPass123!")
    Membership.objects.create(
        user=user, tenant=public_tenant, role=Membership.Role.EDITOR
    )
    return user


@pytest.fixture
def viewer(public_tenant):
    user = User.objects.create_user("f04_viewer", "f04v@test.com", "TestPass123!")
    Membership.objects.create(
        user=user, tenant=public_tenant, role=Membership.Role.VIEWER
    )
    return user


@pytest.fixture
def session(public_tenant):
    return make_session(tenant=public_tenant, status=SessionStatus.READY)


def ticket_url(session) -> str:
    return f"{SESSIONS}{session.pk}/live-ticket/"


def precheck(session, settings, *, ticket: str = "") -> dict:
    """What the agent sees at handshake.

    Driven through the real endpoint, service-token authenticated, exactly as
    the agent calls it. A helper that returned the right dict into a response
    nobody assembles is the failure this is here to catch — and it caught one:
    the auth block was first written between `@api_view` and the view, which
    made the *helper* the endpoint.
    """
    settings.OIA_SERVICE_TOKEN = "test-service-token"
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    query = f"?ticket={ticket}" if ticket else ""
    response = client.get(
        f"{SESSIONS}{session.pk}/live-precheck/{query}",
        HTTP_X_SERVICE_TOKEN="test-service-token",
        HTTP_X_TENANT_ID=str(session.tenant_id),
    )
    assert response.status_code == 200, response.data
    return response.data


# ── Minting ──────────────────────────────────────────────────────────


def test_an_editor_can_mint_a_ticket(editor, session):
    response = client_for(editor).post(ticket_url(session))

    assert response.status_code == 201, response.data
    assert response.data["ticket"]
    assert response.data["usable_seconds"] == USABLE_SECONDS
    assert response.data["valid_until"]


def test_a_viewer_cannot_mint_a_ticket(viewer, session):
    """A ticket is permission to open the live socket, so it is gated exactly
    as running the meeting is. An action missing from `role_permissions` falls
    back to bare IsAuthenticated, which is the hole review caught on B-06."""
    assert client_for(viewer).post(ticket_url(session)).status_code == 403


def test_the_ticket_is_not_the_session_jwt(editor, session):
    """A-02's point. Whatever this is, it must not be something that opens the
    rest of the API — it is going into a log file."""
    ticket = client_for(editor).post(ticket_url(session)).data["ticket"]

    assert ticket.count(".") != 2, "a three-part dotted value is a JWT"

    api = APIClient()
    api.defaults["SERVER_NAME"] = "localhost"
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {ticket}")
    assert api.get(SESSIONS).status_code in (401, 403)


def test_the_claims_carry_what_the_handshake_needs(editor, session):
    ticket, claims = mint(session=session, user=editor, role="editor")

    resolved = resolve(ticket)

    assert resolved == claims
    assert resolved.session_id == str(session.pk)
    assert resolved.tenant_id == str(session.tenant_id)
    assert resolved.company_id == str(session.company_id)
    assert resolved.role == "editor"


def test_an_unknown_ticket_resolves_to_nothing(editor, session):
    assert resolve("not-a-ticket") is None
    assert resolve("") is None


# ── What the agent reads at handshake ────────────────────────────────


def test_the_precheck_reports_a_valid_ticket(editor, session, settings):
    ticket = client_for(editor).post(ticket_url(session)).data["ticket"]

    auth = precheck(session, settings, ticket=ticket)["auth"]

    assert auth["valid"] is True
    assert auth["tenant_id"] == str(session.tenant_id)
    assert auth["company_id"] == str(session.company_id)
    assert auth["role"] == "editor"
    assert auth["valid_until"]


def test_the_precheck_refuses_a_missing_ticket(session, settings):
    """The shape is uniform whether or not a ticket was sent, so the agent
    never has to tell "this deploy sends no auth" from "this ticket is bad".
    The first would be a reason to fail open, and failing open on
    authentication is how a gate becomes decorative."""
    auth = precheck(session, settings)["auth"]

    assert auth["valid"] is False
    assert auth["reason"]


def test_a_ticket_for_another_session_is_refused(
    editor, session, settings, public_tenant
):
    """The check that stops a ticket being a skeleton key for every session in
    a tenant."""
    # A second tenant, because B-01 allows one active session per company and
    # a Company is unique per tenant — two live sessions cannot share either.
    # Cross-tenant makes the check stronger than the same-tenant case would:
    # the ticket is refused on the session it names, before tenancy is even
    # considered.
    from tenants.models import Tenant

    other_tenant = Tenant.objects.create(name="F04 Other", schema_name="f04_other")
    other = make_session(tenant=other_tenant, status=SessionStatus.READY)
    ticket, _ = mint(session=other, user=editor, role="editor")

    auth = precheck(session, settings, ticket=ticket)["auth"]

    assert auth["valid"] is False
    assert auth["reason"] == "ticket_session_mismatch"


def test_the_precheck_still_answers_its_other_questions(editor, session, settings):
    """One call decides the whole handshake. If approval and consent stopped
    travelling with the auth block, the agent would need a second read — and
    two reads to decide one thing is two chances to decide it on a stale
    half."""
    ticket = client_for(editor).post(ticket_url(session)).data["ticket"]

    body = precheck(session, settings, ticket=ticket)

    assert "approved" in body
    assert "consent" in body
    assert "auth" in body


def test_the_auth_block_is_present_on_every_branch(session, settings):
    """A session with no questionnaire takes the early return. A caller that
    finds `auth` on one response and not another has to guess."""
    session.questionnaire = None
    session.save(update_fields=["questionnaire"])

    body = precheck(session, settings)

    assert body["approved"] is False
    assert "auth" in body
