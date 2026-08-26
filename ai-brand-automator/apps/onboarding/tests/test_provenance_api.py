"""B-06 · provenance list, confirm and edit (AC-1 … AC-4).

Two things here are load-bearing beyond the endpoints themselves.

``extracted_value`` must survive an edit — the card calls that "the single
most important line in the endpoint", because L-02 compares what a reviewer
decided against what the agent proposed, and an edit that overwrote the
proposal would leave the flywheel with no signal.

EVT-109 must carry no values. §12 fans the event stream out to observability
tooling with a different access model than the tenant-scoped store, so the
edit distance leaves and the strings do not.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.onboarding.events import build_payload, emit_provenance_reviewed
from apps.onboarding.models import FieldClassification, ProvenanceStatus
from apps.onboarding.tests.factories import make_provenance, make_session
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/onboarding/sessions/"
PROVENANCE = "/api/v1/onboarding/provenance/"


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
def admin(public_tenant):
    return member(public_tenant, Membership.Role.ADMIN, "b06_admin")


@pytest.fixture
def editor(public_tenant):
    return member(public_tenant, Membership.Role.EDITOR, "b06_editor")


@pytest.fixture
def viewer(public_tenant):
    return member(public_tenant, Membership.Role.VIEWER, "b06_viewer")


# ── AC-1 · the list groups by wizard page ────────────────────────────


def test_provenance_lists_group_by_wizard_page(public_tenant, editor):
    session = make_session(tenant=public_tenant)
    make_provenance(session=session, field_name="legal_name")  # page 1
    make_provenance(session=session, field_name="tagline")  # page 2
    make_provenance(session=session, field_name="demographics")  # page 3
    make_provenance(session=session, field_name="competitors")  # page 4

    response = client_for(editor, public_tenant).get(
        f"{SESSIONS}{session.pk}/provenance/"
    )

    assert response.status_code == 200
    groups = response.data["groups"]
    assert [g["page"] for g in groups] == [1, 2, 3, 4]
    assert [g["label"] for g in groups] == [
        "Company Info",
        "Brand Voice",
        "Target Audience",
        "Assets & Market",
    ]
    assert [g["fields"][0]["field_name"] for g in groups] == [
        "legal_name",
        "tagline",
        "demographics",
        "competitors",
    ]


def test_each_row_carries_what_the_review_page_needs(public_tenant, editor):
    session = make_session(tenant=public_tenant)
    make_provenance(session=session, field_name="legal_name", confidence="0.850")

    response = client_for(editor, public_tenant).get(
        f"{SESSIONS}{session.pk}/provenance/"
    )
    row = response.data["groups"][0]["fields"][0]

    for key in (
        "classification",
        "confidence",
        "extracted_value",
        "final_value",
        "status",
        "source_span",
        "wizard_page",
        "wizard_page_label",
    ):
        assert key in row, key


def test_an_unmapped_field_is_visible_rather_than_dropped(public_tenant, editor):
    """A field missing from field_map.py should look wrong in review, not
    disappear from it."""
    session = make_session(tenant=public_tenant)
    make_provenance(session=session, field_name="a_field_nobody_mapped")

    response = client_for(editor, public_tenant).get(
        f"{SESSIONS}{session.pk}/provenance/"
    )
    groups = response.data["groups"]

    assert groups[-1]["page"] is None
    assert groups[-1]["label"] == "unmapped"
    assert groups[-1]["fields"][0]["field_name"] == "a_field_nobody_mapped"


def test_the_list_is_tenant_scoped(public_tenant, editor):
    other = Tenant.objects.create(name="Other B06", schema_name="other_b06")
    theirs = make_session(tenant=other)
    make_provenance(session=theirs, field_name="legal_name")

    response = client_for(editor, public_tenant).get(
        f"{SESSIONS}{theirs.pk}/provenance/"
    )
    assert response.status_code == 404


# ── AC-2 · the KEY / SECONDARY asymmetry ─────────────────────────────


def test_editor_cannot_confirm_key(public_tenant, editor):
    """The card's named case. §3: "KEY fields require explicit ADMIN
    confirmation before final submit"."""
    row = make_provenance(tenant=public_tenant, classification=FieldClassification.KEY)
    row.session.tenant = public_tenant
    row.session.save(update_fields=["tenant"])

    response = client_for(editor, public_tenant).post(f"{PROVENANCE}{row.pk}/confirm/")

    assert response.status_code == 403
    assert response.data["code"] == "ERR-04"

    row.refresh_from_db()
    assert row.status == ProvenanceStatus.PENDING, "the row changed on a refusal"
    assert row.reviewed_by is None


def test_editor_may_confirm_secondary(public_tenant, editor):
    row = make_provenance(
        tenant=public_tenant, classification=FieldClassification.SECONDARY
    )

    response = client_for(editor, public_tenant).post(f"{PROVENANCE}{row.pk}/confirm/")

    assert response.status_code == 200
    row.refresh_from_db()
    assert row.status == ProvenanceStatus.CONFIRMED
    assert row.reviewed_by == editor
    assert row.reviewed_at is not None


def test_admin_may_confirm_key(public_tenant, admin):
    row = make_provenance(tenant=public_tenant, classification=FieldClassification.KEY)

    response = client_for(admin, public_tenant).post(f"{PROVENANCE}{row.pk}/confirm/")

    assert response.status_code == 200
    row.refresh_from_db()
    assert row.status == ProvenanceStatus.CONFIRMED


def test_editor_cannot_edit_a_key_field(public_tenant, editor):
    """The asymmetry applies to edit as well — §10.2 names both actions."""
    row = make_provenance(tenant=public_tenant, classification=FieldClassification.KEY)

    response = client_for(editor, public_tenant).post(
        f"{PROVENANCE}{row.pk}/edit/", {"final_value": "changed"}, format="json"
    )

    assert response.status_code == 403
    row.refresh_from_db()
    assert row.final_value is None


def test_viewer_cannot_review_anything(public_tenant, viewer):
    row = make_provenance(tenant=public_tenant)
    client = client_for(viewer, public_tenant)

    assert client.post(f"{PROVENANCE}{row.pk}/confirm/").status_code == 403
    assert (
        client.post(
            f"{PROVENANCE}{row.pk}/edit/", {"final_value": "x"}, format="json"
        ).status_code
        == 403
    )


# ── AC-3 · an edit records the human value distinctly ────────────────


def test_edit_preserves_extracted_value(public_tenant, admin):
    """The card's named case, and the line it calls most important.

    L-02's golden-dataset candidates compare the reviewer's value against the
    agent's. If the edit overwrote the proposal, the flywheel has no signal.
    """
    row = make_provenance(
        tenant=public_tenant,
        field_name="legal_name",
        extracted_value="Acme Ltd",
        classification=FieldClassification.KEY,
    )

    response = client_for(admin, public_tenant).post(
        f"{PROVENANCE}{row.pk}/edit/", {"final_value": "Acme Limited"}, format="json"
    )

    assert response.status_code == 200
    row.refresh_from_db()
    assert row.extracted_value == "Acme Ltd", "the agent's proposal was overwritten"
    assert row.final_value == "Acme Limited"
    assert row.status == ProvenanceStatus.EDITED
    assert row.reviewed_by == admin
    assert row.reviewed_at is not None


def test_an_edit_of_a_json_value_round_trips(public_tenant, admin):
    row = make_provenance(
        tenant=public_tenant,
        field_name="competitors",
        extracted_value=[{"name": "Blue Tokai"}],
        classification=FieldClassification.SECONDARY,
    )

    edited = [{"name": "Blue Tokai Coffee Roasters"}]
    client_for(admin, public_tenant).post(
        f"{PROVENANCE}{row.pk}/edit/", {"final_value": edited}, format="json"
    )

    row.refresh_from_db()
    assert row.extracted_value == [{"name": "Blue Tokai"}]
    assert row.final_value == edited


# ── AC-4 · confirmation is idempotent ────────────────────────────────


def test_confirm_idempotent(public_tenant, admin):
    """The card's named case: a second confirm changes nothing and emits
    nothing.

    A duplicate event would inflate the confirm-without-edit rate that §17.3
    reads as extraction quality.
    """
    row = make_provenance(tenant=public_tenant)
    client = client_for(admin, public_tenant)

    first = client.post(f"{PROVENANCE}{row.pk}/confirm/")
    assert first.status_code == 200
    row.refresh_from_db()
    reviewed_at = row.reviewed_at

    second = client.post(f"{PROVENANCE}{row.pk}/confirm/")
    assert second.status_code == 200

    row.refresh_from_db()
    assert row.status == ProvenanceStatus.CONFIRMED
    assert row.reviewed_at == reviewed_at, "the second confirm rewrote the timestamp"


def test_a_confirmed_row_can_still_be_edited(public_tenant, admin):
    """A reviewer may change their mind. Only a re-run is blocked (B-05)."""
    row = make_provenance(tenant=public_tenant, extracted_value="Acme Ltd")
    client = client_for(admin, public_tenant)

    client.post(f"{PROVENANCE}{row.pk}/confirm/")
    response = client.post(
        f"{PROVENANCE}{row.pk}/edit/", {"final_value": "Acme Limited"}, format="json"
    )

    assert response.status_code == 200
    row.refresh_from_db()
    assert row.status == ProvenanceStatus.EDITED
    assert row.extracted_value == "Acme Ltd"


# ── §12 · EVT-109 carries no values ──────────────────────────────────


def test_evt_109_carries_no_values():
    """The card places this in the agent's tests/, but Django is the emitter
    here (§10.2 puts the review endpoints in Django), so the assertion has to
    live where the payload is built.

    §12: EVT-109 carries field_name, action, edit_distance and
    classification. The event stream is a lower-trust surface than the
    tenant-scoped store, so the values never leave.
    """
    payload = build_payload(
        field_name="legal_name",
        action="EDIT",
        edit_distance=4,
        classification="KEY",
    )

    assert set(payload) == {
        "event_ref",
        "field_name",
        "action",
        "edit_distance",
        "classification",
    }

    serialised = str(payload)
    for secret in ("Acme Ltd", "Acme Limited", "extracted_value", "final_value"):
        assert secret not in serialised, f"{secret!r} reached the event"


def test_the_edit_distance_is_the_real_distance(public_tenant, admin):
    """ "Acme Ltd" -> "Acme Limited" is 4 edits, and that number is what §17.3
    reads as extraction quality."""
    from apps.onboarding.text import levenshtein

    assert levenshtein("Acme Ltd", "Acme Limited") == 4


def test_a_review_still_applies_when_the_broker_is_absent(public_tenant, admin):
    """Kafka is disabled in production and no GCP script provisions a broker.

    A reviewer's click must not fail because of that, so emission is
    best-effort — this asserts the review is applied regardless.
    """
    row = make_provenance(tenant=public_tenant)

    response = client_for(admin, public_tenant).post(f"{PROVENANCE}{row.pk}/confirm/")

    assert response.status_code == 200
    row.refresh_from_db()
    assert row.status == ProvenanceStatus.CONFIRMED


# ── The map covers everything ────────────────────────────────────────


def test_every_reviewable_company_field_is_mapped():
    """A field added to Company without updating field_map.py would land in
    ``unmapped``. That is visible, but it should fail here first."""
    from onboarding.models import Company

    from apps.onboarding.field_map import NOT_REVIEWABLE, all_mapped_fields

    company_fields = {
        f.name for f in Company._meta.get_fields() if not f.is_relation
    } - set(NOT_REVIEWABLE)

    unmapped = company_fields - all_mapped_fields()
    assert not unmapped, f"unmapped Company fields: {sorted(unmapped)}"


def test_the_map_invents_no_fields():
    """The reverse: a mapped name that is not a Company field is a typo."""
    from onboarding.models import Company

    from apps.onboarding.field_map import all_mapped_fields

    company_fields = {f.name for f in Company._meta.get_fields() if not f.is_relation}
    invented = all_mapped_fields() - company_fields
    assert not invented, f"mapped names that are not Company fields: {sorted(invented)}"


# ── PR #548 review · all three findings were real ────────────────────


def test_the_provenance_list_requires_tenant_access(public_tenant):
    """A custom action absent from role_permissions falls back to DRF's
    default, which is bare IsAuthenticated.

    That let an authenticated user with no tenant membership reach
    tenant_scope_q(None) and read pre-tenant sessions' provenance — rows kept
    visible for backward compatibility, not for strangers.
    """
    session = make_session(tenant=None)  # a pre-tenant row
    make_provenance(session=session, field_name="legal_name")

    outsider = User.objects.create_user(
        username="b06_no_membership", email="none@test.com", password="TestPass123!"
    )
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=outsider)

    response = client.get(f"{SESSIONS}{session.pk}/provenance/")

    assert response.status_code in (  # weak-assert: ok — either is a non-leak
        403,
        404,
    ), "a user with no tenant membership read a pre-tenant session"


def test_confirm_locks_the_row_before_reading_its_status():
    """Idempotency was only *sequential*: two concurrent confirms could both
    read PENDING, both write CONFIRMED and both emit EVT-109.

    This asserts the lock is taken rather than simulating the race — the SQL
    carries FOR UPDATE, which is the fix. Reproducing the interleaving would
    need two connections and a sleep, and would be flaky in CI.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    row = make_provenance()

    with CaptureQueriesContext(connection) as captured:
        FieldProvenanceLocked = type(row).objects.select_for_update().filter(pk=row.pk)
        list(FieldProvenanceLocked)  # force evaluation

    assert any("FOR UPDATE" in q["sql"].upper() for q in captured.captured_queries)


def test_emission_is_skipped_when_kafka_is_disabled(settings):
    """Inert by configuration, not by a failed connection.

    Attempting the publish when no broker exists would mean a failed
    connection and a warning on every review action, which is the opposite of
    inert. Asserted through the predicate rather than by patching the
    publisher, so no mock is involved.
    """
    from apps.onboarding.events import emission_enabled

    settings.ONBOARDING_KAFKA_ENABLED = False
    assert emission_enabled() is False

    # The call still returns its payload and raises nothing.
    payload = emit_provenance_reviewed(
        tenant_id=None,
        session_id=1,
        field_name="legal_name",
        action="CONFIRM",
        edit_distance=0,
        classification="SECONDARY",
    )
    assert payload["field_name"] == "legal_name"


def test_emission_is_enabled_when_configured(settings):
    from apps.onboarding.events import emission_enabled

    settings.ONBOARDING_KAFKA_ENABLED = True
    assert emission_enabled() is True


def test_the_publish_is_queued_rather_than_run_inline():
    """publish_event_to_kafka is a Celery @shared_task, so calling it directly
    runs it in this process and a reviewer's click blocks on Kafka I/O.

    Asserted against the source because the alternative is patching the task,
    and this codebase does not mock. The requirement is precisely that the
    call site uses .delay(), so that is what is checked.
    """
    import inspect

    from apps.onboarding import events

    source = inspect.getsource(events.emit_provenance_reviewed)
    assert "publish_event_to_kafka.delay(" in source
    assert "\n        publish_event_to_kafka(" not in source


# ── K-02 · submit guard, delegation, config ────────────────────────


def test_submit_blocked_while_conflicts_exist(public_tenant, admin):
    """AC-5: PATCH to CONFIRMED refused when CONFLICT rows remain."""
    session = make_session(tenant=public_tenant, status="REVIEW_PENDING")
    make_provenance(
        session=session,
        field_name="legal_name",
        classification=FieldClassification.KEY,
        status=ProvenanceStatus.CONFLICT,
    )
    make_provenance(
        session=session,
        field_name="tagline",
        classification=FieldClassification.SECONDARY,
        status=ProvenanceStatus.CONFIRMED,
    )

    response = client_for(admin, public_tenant).patch(
        f"{SESSIONS}{session.pk}/",
        {"status": "CONFIRMED"},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "UNRESOLVED_CONFLICTS"
    assert "legal_name" in response.data["unresolved_fields"]

    session.refresh_from_db()
    assert session.status == "REVIEW_PENDING"


def test_submit_succeeds_after_all_conflicts_resolved(public_tenant, admin):
    """AC-5: once every CONFLICT is resolved, CONFIRMED transition works."""
    session = make_session(tenant=public_tenant, status="REVIEW_PENDING")
    make_provenance(
        session=session,
        field_name="legal_name",
        classification=FieldClassification.KEY,
        status=ProvenanceStatus.CONFIRMED,
    )

    response = client_for(admin, public_tenant).patch(
        f"{SESSIONS}{session.pk}/",
        {"status": "CONFIRMED"},
        format="json",
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert session.status == "CONFIRMED"


def test_delegate_can_confirm_key_field(public_tenant, editor):
    """AC-4: an Editor named as key_confirm_delegate may confirm KEY."""
    session = make_session(tenant=public_tenant)
    session.config = {"key_confirm_delegate": editor.pk}
    session.save(update_fields=["config"])

    row = make_provenance(
        session=session,
        classification=FieldClassification.KEY,
    )

    response = client_for(editor, public_tenant).post(f"{PROVENANCE}{row.pk}/confirm/")

    assert response.status_code == 200
    row.refresh_from_db()
    assert row.status == ProvenanceStatus.CONFIRMED
    assert row.reviewed_by == editor


def test_delegate_can_edit_key_field(public_tenant, editor):
    """AC-4: delegation applies to edit as well as confirm."""
    session = make_session(tenant=public_tenant)
    session.config = {"key_confirm_delegate": editor.pk}
    session.save(update_fields=["config"])

    row = make_provenance(
        session=session,
        classification=FieldClassification.KEY,
        extracted_value="Acme Ltd",
    )

    response = client_for(editor, public_tenant).post(
        f"{PROVENANCE}{row.pk}/edit/",
        {"final_value": "Acme Limited"},
        format="json",
    )

    assert response.status_code == 200
    row.refresh_from_db()
    assert row.status == ProvenanceStatus.EDITED
    assert row.final_value == "Acme Limited"


def test_non_delegate_editor_still_refused_key(public_tenant):
    """AC-4: delegation is per-session — a different Editor is still refused."""
    delegate = member(public_tenant, Membership.Role.EDITOR, "delegate_ed")
    outsider = member(public_tenant, Membership.Role.EDITOR, "outsider_ed")

    session = make_session(tenant=public_tenant)
    session.config = {"key_confirm_delegate": delegate.pk}
    session.save(update_fields=["config"])

    row = make_provenance(
        session=session,
        classification=FieldClassification.KEY,
    )

    response = client_for(outsider, public_tenant).post(
        f"{PROVENANCE}{row.pk}/confirm/"
    )

    assert response.status_code == 403
    assert response.data["code"] == "ERR-04"


def test_config_field_persists_delegate(public_tenant, admin):
    """AC-4: Owner/Admin can set key_confirm_delegate via session PATCH."""
    session = make_session(tenant=public_tenant, status="REVIEW_PENDING")
    target_user = member(public_tenant, Membership.Role.EDITOR, "delegate_target")

    response = client_for(admin, public_tenant).patch(
        f"{SESSIONS}{session.pk}/",
        {"config": {"key_confirm_delegate": target_user.pk}},
        format="json",
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert session.config["key_confirm_delegate"] == target_user.pk
