"""B-04 · the session endpoints (AC-1, AC-2, AC-3).

The API is the part the Onboarding Interface depends on without being trusted
to know §9.4, so these drive it over real HTTP against real Postgres rather
than calling the viewset directly.

Auth follows the platform pattern from ``orchestration/tests/test_views.py``:
force-authenticate and pass the tenant in ``X-Tenant-ID``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.onboarding.models import OnboardingSession
from apps.onboarding.tests.factories import make_company, make_session
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
    return member(public_tenant, Membership.Role.EDITOR, "b04_editor")


@pytest.fixture
def viewer(public_tenant):
    return member(public_tenant, Membership.Role.VIEWER, "b04_viewer")


# ── AC-1 · the endpoints exist with the documented shapes ────────────


def test_create_read_patch_and_list(public_tenant, editor):
    client = client_for(editor, public_tenant)
    company = make_company(tenant=public_tenant)

    created = client.post(SESSIONS, {"company": company.pk}, format="json")
    assert created.status_code == 201, created.data
    session_id = created.data["id"]
    assert created.data["status"] == "DRAFT"

    read = client.get(f"{SESSIONS}{session_id}/")
    assert read.status_code == 200
    assert read.data["company"] == company.pk

    patched = client.patch(
        f"{SESSIONS}{session_id}/", {"status": "PREPARING"}, format="json"
    )
    assert patched.status_code == 200, patched.data
    assert patched.data["status"] == "PREPARING"

    listed = client.get(SESSIONS)
    assert listed.status_code == 200
    ids = [row["id"] for row in listed.data.get("results", listed.data)]
    assert session_id in ids


def test_list_filters_by_company(public_tenant, editor):
    # Company.tenant is a OneToOneField — one company per tenant — so two
    # companies cannot share this tenant. They are left tenant-less (the
    # pre-tenant case tenant_scope_q keeps visible) and the sessions carry
    # the tenant instead.
    client = client_for(editor, public_tenant)
    wanted = make_session(
        company=make_company(tenant=None, name="Wanted"), tenant=public_tenant
    )
    make_session(company=make_company(tenant=None, name="Other"), tenant=public_tenant)

    response = client.get(SESSIONS, {"company": wanted.company_id})
    rows = response.data.get("results", response.data)

    assert response.status_code == 200
    assert [row["id"] for row in rows] == [wanted.pk]


def test_the_endpoints_appear_in_the_openapi_schema(public_tenant, editor):
    """AC-1's schema half, via DRF's built-in generator.

    No drf-spectacular or drf-yasg is installed and no schema endpoint is
    routed, so this asserts against ``rest_framework.schemas.openapi`` rather
    than adding a dependency for one assertion.
    """
    from rest_framework.schemas.openapi import SchemaGenerator

    schema = SchemaGenerator().get_schema(public=True)
    paths = schema["paths"]

    assert SESSIONS in paths, sorted(p for p in paths if "onboarding" in p)
    assert {"get", "post"} <= set(paths[SESSIONS])

    detail = f"{SESSIONS}{{id}}/"
    assert detail in paths
    assert {"get", "patch"} <= set(paths[detail])


def test_legal_next_states_are_advertised(public_tenant, editor):
    """So a caller does not have to hold the state diagram in its head."""
    session = make_session(tenant=public_tenant, status="READY")
    response = client_for(editor, public_tenant).get(f"{SESSIONS}{session.pk}/")

    assert response.status_code == 200
    assert response.data["legal_next_states"] == ["ESCALATED", "MEETING_LIVE"]


# ── AC-2 · illegal transitions are refused with 409 ──────────────────


def test_illegal_transition_409(public_tenant, editor):
    """The card's named case, and AC-2's worked example."""
    session = make_session(tenant=public_tenant, status="READY")
    client = client_for(editor, public_tenant)

    response = client.patch(
        f"{SESSIONS}{session.pk}/", {"status": "CONFIRMED"}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "ERR-18"
    assert response.data["current_state"] == "READY"
    assert response.data["legal_next_states"] == ["ESCALATED", "MEETING_LIVE"]

    session.refresh_from_db()
    assert session.status == "READY", "the refused transition still wrote"


def test_a_refused_transition_does_not_apply_other_fields(public_tenant, editor):
    """A 409 with the rest half-applied would be worse than a clean refusal."""
    session = make_session(tenant=public_tenant, status="READY")
    client = client_for(editor, public_tenant)

    response = client.patch(
        f"{SESSIONS}{session.pk}/",
        {"status": "COMPLETED", "evidence_manifest_hash": "should-not-persist"},
        format="json",
    )

    assert response.status_code == 409
    session.refresh_from_db()
    assert session.evidence_manifest_hash == ""


def test_a_second_active_session_is_409(public_tenant, editor):
    """The B-01 partial index, surfaced as ERR-06 rather than a 500."""
    company = make_company(tenant=public_tenant)
    make_session(company=company, status="DRAFT")
    client = client_for(editor, public_tenant)

    response = client.post(SESSIONS, {"company": company.pk}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "ERR-06"


def test_prompt_versions_cannot_be_set_by_a_client(public_tenant, editor):
    """§17.2: L-03 writes it. A client able to set it could change which
    prompt versions a live meeting runs under — the thing pinning prevents."""
    session = make_session(tenant=public_tenant, status="DRAFT")
    client = client_for(editor, public_tenant)

    response = client.patch(
        f"{SESSIONS}{session.pk}/",
        {"prompt_versions": {"oia.generate_questionnaire": "v99"}},
        format="json",
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert session.prompt_versions == {}


def test_escalated_from_cannot_be_set_by_a_client(public_tenant, editor):
    session = make_session(tenant=public_tenant, status="READY")
    client = client_for(editor, public_tenant)

    client.patch(
        f"{SESSIONS}{session.pk}/", {"escalated_from": "PROCESSING"}, format="json"
    )

    session.refresh_from_db()
    assert session.escalated_from is None


# ── AC-3 · roles and tenant scoping ──────────────────────────────────


def test_viewer_may_read(public_tenant, viewer):
    session = make_session(tenant=public_tenant)
    client = client_for(viewer, public_tenant)

    assert client.get(SESSIONS).status_code == 200
    assert client.get(f"{SESSIONS}{session.pk}/").status_code == 200


def test_viewer_is_refused_writes(public_tenant, viewer):
    session = make_session(tenant=public_tenant)
    # Tenant-less: make_session above already claimed this tenant's company.
    company = make_company(tenant=None, name="Viewer Co")
    client = client_for(viewer, public_tenant)

    assert (
        client.post(SESSIONS, {"company": company.pk}, format="json").status_code == 403
    )
    assert (
        client.patch(
            f"{SESSIONS}{session.pk}/", {"status": "PREPARING"}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "role", [Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.EDITOR]
)
def test_owner_admin_and_editor_may_write(public_tenant, role):
    user = member(public_tenant, role, f"b04_{role}")
    client = client_for(user, public_tenant)
    company = make_company(tenant=None, name=f"Co {role}")

    created = client.post(SESSIONS, {"company": company.pk}, format="json")
    assert created.status_code == 201, (role, created.data)

    patched = client.patch(
        f"{SESSIONS}{created.data['id']}/", {"status": "PREPARING"}, format="json"
    )
    assert patched.status_code == 200, (role, patched.data)


def test_cross_tenant_returns_404(public_tenant, editor):
    """The card's named case: 404 rather than 403, so the API does not
    confirm that another tenant's session exists."""
    other = Tenant.objects.create(name="Other Co", schema_name="other_b04")
    theirs = make_session(company=make_company(tenant=other, name="Theirs"))
    client = client_for(editor, public_tenant)

    assert client.get(f"{SESSIONS}{theirs.pk}/").status_code == 404
    assert (
        client.patch(
            f"{SESSIONS}{theirs.pk}/", {"status": "PREPARING"}, format="json"
        ).status_code
        == 404
    )


def test_a_list_never_leaks_another_tenants_session(public_tenant, editor):
    other = Tenant.objects.create(name="Leak Co", schema_name="leak_b04")
    theirs = make_session(company=make_company(tenant=other, name="Leak"))
    mine = make_session(tenant=public_tenant)

    response = client_for(editor, public_tenant).get(SESSIONS)
    ids = [row["id"] for row in response.data.get("results", response.data)]

    assert mine.pk in ids
    assert theirs.pk not in ids


def test_anonymous_is_refused():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    assert client.get(SESSIONS).status_code in (401, 403)


# ── AC-4 · escalation over HTTP ──────────────────────────────────────


def test_escalation_round_trips_through_the_api(public_tenant, editor):
    """AC-4 end to end: a session escalated out of PROCESSING resumes there,
    not at the start."""
    session = make_session(tenant=public_tenant, status="GATHERED")
    client = client_for(editor, public_tenant)
    url = f"{SESSIONS}{session.pk}/"

    assert client.patch(url, {"status": "PROCESSING"}, format="json").status_code == 200
    assert client.patch(url, {"status": "ESCALATED"}, format="json").status_code == 200

    escalated = client.get(url)
    assert escalated.data["status"] == "ESCALATED"
    assert escalated.data["escalated_from"] == "PROCESSING"
    assert escalated.data["legal_next_states"] == ["PROCESSING"]

    resumed = client.patch(url, {"status": "PROCESSING"}, format="json")
    assert resumed.status_code == 200
    assert resumed.data["status"] == "PROCESSING"
    assert resumed.data["escalated_from"] is None


def test_a_full_lifecycle_walks_the_state_machine(public_tenant, editor):
    """E2E: DRAFT to COMPLETED through the API alone."""
    company = make_company(tenant=None, name="Lifecycle Co")
    client = client_for(editor, public_tenant)

    created = client.post(SESSIONS, {"company": company.pk}, format="json")
    url = f"{SESSIONS}{created.data['id']}/"

    for target in (
        "PREPARING",
        "READY",
        "MEETING_LIVE",
        "GATHERED",
        "PROCESSING",
        "REVIEW_PENDING",
        "CONFIRMED",
        "COMPLETED",
    ):
        response = client.patch(url, {"status": target}, format="json")
        assert response.status_code == 200, (target, response.data)
        assert response.data["status"] == target

    session = OnboardingSession.objects.get(pk=created.data["id"])
    assert session.is_terminal


# ── PR #546 review · the update path is all-or-nothing ───────────────


def test_a_serializer_error_does_not_leave_the_status_changed(public_tenant, editor):
    """A legal transition alongside an invalid field must write neither.

    The first version applied the transition, saved it, and only then let the
    serializer validate — so this returned 400 with the status already
    committed. The inverse case (illegal transition, nothing applied) was
    tested; this direction was not.
    """
    session = make_session(tenant=public_tenant, status="DRAFT")
    client = client_for(editor, public_tenant)

    response = client.patch(
        f"{SESSIONS}{session.pk}/",
        {
            "status": "PREPARING",  # legal
            "evidence_manifest_hash": "x" * 200,  # max_length is 64
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    session.refresh_from_db()
    assert session.status == "DRAFT", "the status was committed before validation"
    assert session.evidence_manifest_hash == ""


def test_an_escalation_is_not_recorded_when_the_rest_is_invalid(public_tenant, editor):
    """escalated_from must not be written by a request that fails."""
    session = make_session(tenant=public_tenant, status="READY")
    client = client_for(editor, public_tenant)

    response = client.patch(
        f"{SESSIONS}{session.pk}/",
        {"status": "ESCALATED", "evidence_manifest_hash": "y" * 200},
        format="json",
    )

    assert response.status_code == 400
    session.refresh_from_db()
    assert session.status == "READY"
    assert session.escalated_from is None
