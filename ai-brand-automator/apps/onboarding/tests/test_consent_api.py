"""B-07 · the consent API (AC-1 … AC-4).

Consent is the prerequisite IG-08 checks before a recording can start, so
these tests are about lawfulness being provable after the fact rather than
about CRUD. Two of them matter more than the rest.

``granted_at`` must be the server's. FR-REC-01 says so, and a client-chosen
consent timestamp is the single field an incident would turn on.

Consent must not be inherited between sessions. The card calls AC-4 "the one
people get wrong": consent attaches to the conversation being recorded, not to
the customer relationship, and inheriting it would be both a GDPR problem and
a product problem.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.onboarding.commands import (
    CLOSE_CODE_CONSENT_REVOKED,
    build_consent_revoked,
    commands_enabled,
)
from apps.onboarding.models import ConsentMethod, ConsentRecord, SessionStatus
from apps.onboarding.tests.factories import make_company, make_consent, make_session
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/onboarding/sessions/"


def client_for(user, tenant) -> APIClient:
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return client


def member(tenant, role, username) -> User:
    user = User.objects.create_user(
        username=username, email=f"{username}@test.com", password="TestPass123!"
    )
    Membership.objects.create(user=user, tenant=tenant, role=role)
    return user


@pytest.fixture
def editor(public_tenant):
    return member(public_tenant, Membership.Role.EDITOR, "b07_editor")


@pytest.fixture
def viewer(public_tenant):
    return member(public_tenant, Membership.Role.VIEWER, "b07_viewer")


def consent_url(session) -> str:
    return f"{SESSIONS}{session.pk}/consent/"


def precheck(session, settings) -> dict:
    """What the agent sees. Service-token authenticated, like the agent's call.

    Driven through the real endpoint rather than by calling `_consent_block`,
    because the thing worth proving is that the agent's *response* carries it —
    a helper that returns the right dict into a response nobody assembles is
    the failure this is meant to catch.
    """
    settings.OIA_SERVICE_TOKEN = "test-service-token"
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    response = client.get(
        f"{SESSIONS}{session.pk}/live-precheck/",
        HTTP_X_SERVICE_TOKEN="test-service-token",
        HTTP_X_TENANT_ID=str(session.tenant_id),
    )
    assert response.status_code == 200, response.data
    return response.data


VALID_BODY = {
    "subject_name": "Asha Kalyani",
    "method": ConsentMethod.VERBAL_RECORDED,
    "scope": {"audio": True, "transcript": True, "captured_media": False},
}


# ── AC-1 · consent captures who, how and what ────────────────────────


def test_consent_records_subject_method_and_scope(public_tenant, editor):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    response = client_for(editor, public_tenant).post(
        consent_url(session), VALID_BODY, format="json"
    )

    assert response.status_code == 201, response.data
    assert response.data["subject_name"] == "Asha Kalyani"
    assert response.data["method"] == ConsentMethod.VERBAL_RECORDED
    assert response.data["scope"]["captured_media"] is False
    assert response.data["granted_by"] == editor.pk
    assert response.data["is_active"] is True


def test_granted_at_server_side(public_tenant, editor):
    """The card's named case: a client cannot backdate consent.

    Not merely ignored — the serializer does not accept the field at all, so
    there is no code path that could start trusting it.
    """
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    forged = timezone.now() - timedelta(days=400)

    response = client_for(editor, public_tenant).post(
        consent_url(session),
        {**VALID_BODY, "granted_at": forged.isoformat()},
        format="json",
    )

    assert response.status_code == 201
    granted_at = session.consent_records.get().granted_at
    assert granted_at != forged
    assert (timezone.now() - granted_at).total_seconds() < 60


def test_granted_by_cannot_be_supplied_by_a_client(public_tenant, editor):
    """Consent recorded in someone else's name would be worse than none."""
    other = member(public_tenant, Membership.Role.EDITOR, "b07_other")
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    client_for(editor, public_tenant).post(
        consent_url(session), {**VALID_BODY, "granted_by": other.pk}, format="json"
    )

    assert session.consent_records.get().granted_by == editor


def test_a_second_grant_returns_the_existing_record(public_tenant, editor):
    """Two consent rows for one conversation would make "was this lawful?"
    ambiguous, so a repeat grant is idempotent rather than additive."""
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    client = client_for(editor, public_tenant)

    first = client.post(consent_url(session), VALID_BODY, format="json")
    second = client.post(consent_url(session), VALID_BODY, format="json")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert session.consent_records.count() == 1


@pytest.mark.parametrize(
    "bad_scope",
    [
        {"retention_days": 0},  # below the minimum
        {"retention_days": 99999},  # above the maximum
        {"audio": "yes please"},  # not a boolean
        ["not", "an", "object"],
    ],
)
def test_a_malformed_scope_is_refused(public_tenant, editor, bad_scope):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    response = client_for(editor, public_tenant).post(
        consent_url(session), {**VALID_BODY, "scope": bad_scope}, format="json"
    )

    assert response.status_code == 400
    assert "scope" in response.data


def test_an_unlisted_scope_key_is_kept(public_tenant, editor):
    """scope is JSON so it can grow without a migration — this serializer
    must not be the thing that drops the growth."""
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    client_for(editor, public_tenant).post(
        consent_url(session),
        {**VALID_BODY, "scope": {"audio": True, "future_key": "kept"}},
        format="json",
    )

    assert session.consent_records.get().scope["future_key"] == "kept"


# ── AC-2 · the session exposes consent state ─────────────────────────


def test_a_session_without_consent_reports_granted_false(public_tenant, editor):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    response = client_for(editor, public_tenant).get(f"{SESSIONS}{session.pk}/")

    assert response.data["consent"] == {
        "granted": False,
        "granted_at": None,
        "method": None,
        "scope": None,
    }


def test_a_session_with_consent_reports_the_details(public_tenant, editor):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    client = client_for(editor, public_tenant)
    client.post(consent_url(session), VALID_BODY, format="json")

    consent = client.get(f"{SESSIONS}{session.pk}/").data["consent"]

    assert consent["granted"] is True
    assert consent["granted_at"] is not None
    assert consent["method"] == ConsentMethod.VERBAL_RECORDED
    assert consent["scope"]["transcript"] is True


# ── AC-3 · revocation is immediate and visible ───────────────────────


def test_revocation_flips_the_session_state(public_tenant, editor):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    client = client_for(editor, public_tenant)
    client.post(consent_url(session), VALID_BODY, format="json")

    revoked = client.delete(consent_url(session))

    assert revoked.status_code == 200
    assert revoked.data["revoked_at"] is not None
    assert revoked.data["is_active"] is False
    assert client.get(f"{SESSIONS}{session.pk}/").data["consent"]["granted"] is False


def test_revocation_is_idempotent(public_tenant, editor):
    """A double-click is not a failure."""
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    client = client_for(editor, public_tenant)
    client.post(consent_url(session), VALID_BODY, format="json")

    first = client.delete(consent_url(session))
    revoked_at = session.consent_records.get().revoked_at
    second = client.delete(consent_url(session))

    assert first.status_code == 200
    assert second.status_code == 200
    assert session.consent_records.get().revoked_at == revoked_at


def test_revoking_without_consent_is_not_an_error(public_tenant, editor):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    response = client_for(editor, public_tenant).delete(consent_url(session))

    assert response.status_code == 200
    assert response.data["granted"] is False


def test_revocation_publishes_the_close_command(public_tenant, editor):
    """AC-3's other half, as far as this story can take it.

    The socket close itself is F-04's — ``app/api/ws.py`` still raises
    NotImplementedError, so there is no live session to close. What B-07 owes
    F-04 is a command with the right shape, and that is what this asserts.
    """
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    consent = make_consent(session=session)

    payload = build_consent_revoked(
        session_id=session.pk, tenant_id=public_tenant.id, consent_id=consent.pk
    )

    assert payload["command"] == "consent.revoked"
    assert payload["close_code"] == CLOSE_CODE_CONSENT_REVOKED == 4403
    assert payload["session_id"] == str(session.pk)


def test_the_close_command_carries_no_personal_data():
    """NFR-PRIV-01: a command topic is a lower-trust surface than the
    tenant-scoped store, so it carries ids and not the subject's name."""
    payload = build_consent_revoked(session_id=1, tenant_id=2, consent_id=3)

    assert set(payload) == {
        "command",
        "session_id",
        "tenant_id",
        "consent_id",
        "close_code",
    }
    assert "Asha" not in str(payload)
    assert "subject_name" not in payload


def test_revocation_succeeds_with_commands_disabled(public_tenant, editor, settings):
    """ "A revocation must succeed even if the agent is down" — the technical
    note's requirement, and the reason this is published rather than called."""
    settings.ONBOARDING_KAFKA_ENABLED = False
    assert commands_enabled() is False

    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    client = client_for(editor, public_tenant)
    client.post(consent_url(session), VALID_BODY, format="json")

    response = client.delete(consent_url(session))

    assert response.status_code == 200
    assert session.consent_records.get().revoked_at is not None


# ── AC-4 · consent is per session, not per tenant ────────────────────


def test_consent_not_inherited(public_tenant, editor):
    """The card's named case, and the one it says people get wrong.

    Consent attaches to the conversation being recorded. Inheriting it across
    sessions would be a GDPR problem and a product problem at once.
    """
    company = make_company(tenant=None, name="Repeat Customer")
    client = client_for(editor, public_tenant)

    first = make_session(company=company, tenant=public_tenant, status="READY")
    client.post(consent_url(first), VALID_BODY, format="json")
    assert client.get(f"{SESSIONS}{first.pk}/").data["consent"]["granted"] is True

    # Retire the first so the one-active-session index allows a second.
    first.status = SessionStatus.COMPLETED
    first.save(update_fields=["status"])

    second = make_session(company=company, tenant=public_tenant, status="DRAFT")
    consent = client.get(f"{SESSIONS}{second.pk}/").data["consent"]

    assert consent["granted"] is False, "consent was inherited across sessions"
    assert consent["granted_at"] is None


def test_consent_is_not_shared_between_sessions_of_different_companies(
    public_tenant, editor
):
    client = client_for(editor, public_tenant)
    consented = make_session(
        company=make_company(tenant=None, name="A"), tenant=public_tenant
    )
    client.post(consent_url(consented), VALID_BODY, format="json")

    other = make_session(
        company=make_company(tenant=None, name="B"), tenant=public_tenant
    )
    assert client.get(f"{SESSIONS}{other.pk}/").data["consent"]["granted"] is False


# ── Roles and tenant scoping ─────────────────────────────────────────


def test_viewer_cannot_record_or_revoke_consent(public_tenant, viewer):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    client = client_for(viewer, public_tenant)

    assert (
        client.post(consent_url(session), VALID_BODY, format="json").status_code == 403
    )
    assert client.delete(consent_url(session)).status_code == 403


def test_the_consent_action_requires_tenant_access(public_tenant):
    """A custom action absent from role_permissions would fall through to bare
    IsAuthenticated — the hole review found on B-06."""
    session = make_session(tenant=None)
    outsider = User.objects.create_user(
        username="b07_no_membership", email="n@test.com", password="TestPass123!"
    )
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=outsider)

    response = client.post(consent_url(session), VALID_BODY, format="json")

    # weak-assert: ok — either is a non-leak; pinning one would assert DRF's ordering
    assert response.status_code in (403, 404)


def test_cross_tenant_consent_is_404(public_tenant, editor):
    other = Tenant.objects.create(name="Other B07", schema_name="other_b07")
    theirs = make_session(company=make_company(tenant=other, name="Theirs"))

    response = client_for(editor, public_tenant).post(
        consent_url(theirs), VALID_BODY, format="json"
    )

    assert response.status_code == 404


def test_the_serializer_itself_refuses_the_server_set_fields():
    """Three layers protect granted_at and granted_by, and only two of them
    are exercised by the tests above.

    ``auto_now_add`` makes the model ignore an assigned timestamp, and the view
    passes ``granted_by`` as a save kwarg, which wins over validated_data. So
    those tests would still pass if the serializer stopped declaring these
    read-only — which means they do not prove the serializer layer exists.

    This asserts it directly, so the defence-in-depth stays deliberate rather
    than becoming accidental.
    """
    from apps.onboarding.serializers import ConsentRecordSerializer

    fields = ConsentRecordSerializer().fields
    for name in ("granted_at", "granted_by", "revoked_at"):
        assert fields[name].read_only, f"{name} is writable by a client"


# ── PR #549 review · all four findings were real ─────────────────────


def test_scope_defaults_are_applied(public_tenant, editor):
    """The docstring promised defaults; validate_scope returned the caller's
    dict, so an operator who ticked nothing stored ``{}``.

    A record that does not say what was consented to is the opposite of the
    point of recording consent at all.
    """
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    client_for(editor, public_tenant).post(
        consent_url(session),
        {"subject_name": "Asha Kalyani", "method": ConsentMethod.CHECKBOX, "scope": {}},
        format="json",
    )

    scope = session.consent_records.get().scope
    assert scope["audio"] is True
    assert scope["transcript"] is True
    assert scope["captured_media"] is True


def test_scope_defaults_do_not_overwrite_explicit_values(public_tenant, editor):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    client_for(editor, public_tenant).post(
        consent_url(session),
        {**VALID_BODY, "scope": {"audio": False}},
        format="json",
    )

    scope = session.consent_records.get().scope
    assert scope["audio"] is False, "an explicit value was overwritten by a default"
    assert scope["transcript"] is True, "the default was not applied"


def test_the_session_list_does_not_query_per_session(public_tenant, editor):
    """The list and retrieve endpoints share a serializer, and the consent
    field queried per row — 20 sessions meant 21 queries.

    Asserted by counting, so a regression shows up as a number rather than as
    a slow page nobody attributes to this.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = client_for(editor, public_tenant)
    for name in ("One", "Two", "Three", "Four"):
        session = make_session(
            company=make_company(tenant=None, name=name), tenant=public_tenant
        )
        make_consent(session=session)

    with CaptureQueriesContext(connection) as captured:
        response = client.get(SESSIONS)
        assert response.status_code == 200

    consent_queries = [
        q
        for q in captured.captured_queries
        if "onboarding_sessions_consentrecord" in q["sql"]
    ]
    assert len(consent_queries) <= 1, (
        f"{len(consent_queries)} consent queries for 4 sessions — the prefetch "
        "is not being used"
    )


def test_the_revocation_command_is_published_after_the_commit():
    """The docstring claimed commit-then-notify; the publish ran inside the
    action's atomic block, so the command could be queued before the
    revocation was visible.

    Asserted against the source rather than by patching, because this codebase
    does not mock and the requirement is precisely that the call site defers.
    """
    import inspect

    from apps.onboarding.views import OnboardingSessionViewSet

    source = inspect.getsource(OnboardingSessionViewSet._revoke_consent)
    assert "on_commit(" in source
    assert "\n        publish_consent_revoked(" not in source


# ── F-01 AC-2 · EVT-101, and the precheck the agent reads ────────────


def test_evt101_carries_hash_not_name(public_tenant, editor):
    """AC-2: the event carries "consent_id, method and subject_name_hash —
    never the subject's name".

    The exact key set is asserted, not just the absence of one field. A name
    reaches an event stream because somebody adds a key here for a good
    reason, and it should have to get past an assertion first.
    """
    from apps.onboarding.events import build_consent_payload

    payload = build_consent_payload(
        consent_id=42, method=ConsentMethod.VERBAL_RECORDED, subject_name="Asha Kalyani"
    )

    assert set(payload) == {
        "event_ref",
        "consent_id",
        "method",
        "subject_name_hash",
    }
    assert payload["event_ref"] == "EVT-101"
    serialised = json.dumps(payload)
    assert "Asha" not in serialised
    assert "Kalyani" not in serialised


def test_the_subject_hash_is_keyed_not_a_bare_digest(public_tenant):
    """A plain SHA-256 of a personal name is reversible with a name list.

    The whole promise of `subject_name_hash` is that the event stream cannot
    identify the subject, and an unkeyed digest of "Asha Kalyani" *is* "Asha
    Kalyani" to anyone who thinks to try. Asserted against the bare digest
    rather than by reading the implementation.
    """
    import hashlib

    from apps.onboarding.events import subject_name_hash

    bare = hashlib.sha256("asha kalyani".encode()).hexdigest()

    assert subject_name_hash("Asha Kalyani") != bare


def test_the_same_person_hashes_the_same_way(public_tenant):
    """Correlation is the only reason to carry a hash at all, so casing and
    stray whitespace must not produce two different subjects."""
    from apps.onboarding.events import subject_name_hash

    assert subject_name_hash("Asha Kalyani") == subject_name_hash("  asha   kalyani ")
    assert subject_name_hash("Asha Kalyani") != subject_name_hash("Ada Lovelace")


def test_granting_consent_emits_evt101(public_tenant, editor, settings):
    """The emission is wired to the endpoint, not merely available.

    Asserted through the real POST: a helper nobody calls is the commonest way
    an event goes missing, and the payload builder passing its own unit test
    would not notice.

    A handler is attached to the emitter's own logger rather than using
    `caplog`, because this project configures `apps.onboarding` with
    propagation off — caplog's root handler never sees the record, so the
    assertion would fail whether or not the emitter ran, which is the least
    useful shape a test can have.
    """
    # Pinned, not inherited. This environment has ONBOARDING_KAFKA_ENABLED
    # true, so the emitter took the publish branch and the suppression line
    # never appeared — the first version of this test failed for a reason that
    # had nothing to do with the wiring it was checking.
    settings.ONBOARDING_KAFKA_ENABLED = False
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    emitter_log = logging.getLogger("apps.onboarding.events")
    handler = Capture()
    previous = emitter_log.level
    emitter_log.addHandler(handler)
    emitter_log.setLevel(logging.DEBUG)
    try:
        response = client_for(editor, public_tenant).post(
            consent_url(session), VALID_BODY, format="json"
        )
    finally:
        emitter_log.removeHandler(handler)
        emitter_log.setLevel(previous)

    assert response.status_code == 201, response.data
    # Kafka is disabled in tests, so the suppression line is the observable
    # trace that the emitter ran at all.
    assert any(
        "EVT-101" in record.getMessage() for record in records
    ), "the consent endpoint did not reach the EVT-101 emitter"


def test_a_broker_failure_does_not_fail_the_consent(public_tenant, editor, settings):
    """Consent is already committed by the time EVT-101 is attempted. A broker
    problem must not turn a lawful, captured consent into a 500 the operator
    retries."""
    settings.ONBOARDING_KAFKA_ENABLED = True  # forces the publish path

    response = client_for(editor, public_tenant).post(
        consent_url(make_session(tenant=public_tenant, status=SessionStatus.READY)),
        VALID_BODY,
        format="json",
    )

    assert response.status_code == 201, response.data
    assert ConsentRecord.objects.count() == 1


# ── F-01 AC-3 · what the agent reads ─────────────────────────────────


def test_live_precheck_reports_no_consent(public_tenant, editor, settings):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    body = precheck(session, settings)

    assert body["consent"] == {"present": False, "active": False, "consent_id": None}


def test_live_precheck_reports_active_consent(public_tenant, editor, settings):
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    client_for(editor, public_tenant).post(
        consent_url(session), VALID_BODY, format="json"
    )

    body = precheck(session, settings)

    assert body["consent"]["present"] is True
    assert body["consent"]["active"] is True
    # The name stays in the database, which is the subject-access-request
    # surface. The agent needs to know whether there is consent, never whose.
    assert "Asha" not in json.dumps(body)


def test_live_precheck_reports_revoked_consent(public_tenant, editor, settings):
    """The state IG-08 must refuse. A precheck that reported `present: true`
    and stopped would let a revoked meeting back on air."""
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)
    api = client_for(editor, public_tenant)
    api.post(consent_url(session), VALID_BODY, format="json")
    api.delete(consent_url(session))

    body = precheck(session, settings)

    assert body["consent"]["present"] is True
    assert body["consent"]["active"] is False


def test_consent_is_reported_even_when_the_questionnaire_refuses(
    public_tenant, editor, settings
):
    """Every branch carries the block.

    A caller that finds `consent` on one response and absent on another has to
    guess, and the agent's safe guess — refuse — would show an unapproved
    questionnaire to the operator as a consent error.
    """
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    body = precheck(session, settings)

    assert body["approved"] is False, "fixture should have no approved questionnaire"
    assert "consent" in body
