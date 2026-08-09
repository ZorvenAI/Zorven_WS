"""C-03 · questionnaire storage, its vocabulary and its coverage.

Both cases the card names by file live here — ``test_target_fields_in_vocabulary``
and ``test_wf3_coverage_present``. They are written against the **write
endpoint** rather than against a helper, because the point of both is that a
caller cannot get an invalid set into the database, and a helper only proves
the caller that used it behaved.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.onboarding.field_map import all_mapped_fields
from apps.onboarding.models import (
    DEPTH_NAMES,
    Question,
    Questionnaire,
    QuestionnaireStatus,
    QuestionOrigin,
    QuestionStatus,
    depth_from,
)
from onboarding.models import Company
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

TOKEN = "dev-service-token"
GENERATE = "/api/v1/onboarding/questionnaires/generate/"


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="C03 Co", schema_name="c03_q")


def a_field() -> str:
    """A real field from B-06's vocabulary, so the test cannot drift from it."""
    return sorted(all_mapped_fields())[0]


def questions(count: int = 3, **overrides) -> list[dict]:
    """A minimal valid set: one question per workflow, so WF3 is covered."""
    base = [
        {
            "text": "What do you sell?",
            "workflow_target": "WF1",
            "target_field": a_field(),
        },
        {"text": "What makes you different?", "workflow_target": "WF2"},
        {"text": "Do you have previous ads we can reuse?", "workflow_target": "WF3"},
    ]
    while len(base) < count:
        base.append({"text": f"Filler {len(base)}", "workflow_target": "WF1"})
    return base[:count] if count >= 3 else base


def generate(api_client, tenant, **overrides):
    """Post a valid set as the agent would.

    ``tenant`` is explicit rather than closed over: the header is the thing
    under test in half these cases, and a helper that quietly supplied one
    would hide which tests actually exercise tenant attribution.
    """
    payload = {"questions": questions(), "depth": "standard"}
    payload.update(overrides)
    return api_client.post(
        GENERATE,
        payload,
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )


# ── AC-4 · stored as DRAFT v1 with ordered children ──────────────────


def test_a_generated_set_is_stored_as_draft_version_one(api_client, tenant):
    response = generate(api_client, tenant)

    assert response.status_code == 201, response.content
    row = Questionnaire.objects.get()
    assert row.status == QuestionnaireStatus.DRAFT
    assert row.version == 1
    assert row.question_count == 3


def test_children_are_ordered(api_client, tenant):
    """AC-4 says "with its Question children ordered". The order has to come
    from the database, not from whatever sequence a serializer happened to
    emit."""
    generate(api_client, tenant)

    stored = list(Question.objects.all())

    assert [q.order for q in stored] == [0, 1, 2]
    assert stored[0].text == "What do you sell?"
    assert stored[-1].workflow_target == "WF3"


def test_questions_are_marked_prepared(api_client, tenant):
    """Ad-hoc and follow-up questions arrive during the meeting (D-05, G-06).
    A generated one is PREPARED, and confusing the two would corrupt the
    template reuse D-05 depends on."""
    generate(api_client, tenant)

    assert {q.origin for q in Question.objects.all()} == {QuestionOrigin.PREPARED}
    assert {q.status for q in Question.objects.all()} == {QuestionStatus.OPEN}


def test_a_questionnaire_can_be_stored_without_a_company(api_client, tenant):
    """D1, and the reason the migration exists.

    Prep precedes onboarding: C-01 routes a turn with no session and C-02
    stores a brief keyed on a business name. A NOT NULL company here would
    have made the epic's normal path unstorable.
    """
    response = generate(api_client, tenant)

    assert response.status_code == 201
    assert Questionnaire.objects.get().company is None


def test_a_company_is_attached_when_one_is_named(api_client, tenant):
    company = Company.objects.create(tenant=tenant, name="Kalyani")

    generate(api_client, tenant, company_id=company.pk)

    assert Questionnaire.objects.get().company == company


# ── The card's named case · no invented field names ──────────────────


def test_target_fields_in_vocabulary(api_client, tenant):
    """The card's named case.

    C-03's technical note: target_field "must be drawn from the shared
    apps/onboarding/field_map.py vocabulary introduced in B-06, not invented
    per generation, or J-02 cannot join questions to fields."
    """
    response = api_client.post(
        GENERATE,
        {
            "questions": [
                {
                    "text": "Real field",
                    "workflow_target": "WF1",
                    "target_field": a_field(),
                },
                {
                    "text": "Invented field",
                    "workflow_target": "WF2",
                    "target_field": "vibe_score",
                },
                {"text": "Ads?", "workflow_target": "WF3"},
            ]
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 201
    stored = {q.text: q.target_field for q in Question.objects.all()}
    assert stored["Real field"] == a_field()
    assert stored["Invented field"] == "", "an invented field name was stored"
    assert response.json()["dropped_target_fields"] == ["vibe_score"]


def test_an_invented_field_costs_that_question_not_the_set(api_client, tenant):
    """Rejecting the whole questionnaire over one bad mapping would cost the
    operator every good question in it."""
    response = api_client.post(
        GENERATE,
        {
            "questions": [
                {"text": "A", "workflow_target": "WF1", "target_field": "nonsense"},
                {"text": "B", "workflow_target": "WF2"},
                {"text": "C", "workflow_target": "WF3"},
            ]
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 201
    assert Question.objects.count() == 3


def test_every_stored_target_field_is_in_the_vocabulary_or_empty(api_client, tenant):
    """The invariant behind the case above, stated directly."""
    generate(api_client, tenant)

    vocabulary = all_mapped_fields()
    for question in Question.objects.all():
        # weak-assert: ok — empty-or-valid is the invariant; "" means not applicable
        assert question.target_field == "" or question.target_field in vocabulary


# ── The card's named case · WF3 must be covered ──────────────────────


def test_wf3_coverage_present(api_client, tenant):
    """The card's named case, and FR-PREP-08's hard clause: "a set that covers
    only the five wizard pages fails generation".

    WF3 is the one the requirement review added specifically, and the one a
    model silently drops back to brand-strategy questions without.
    """
    response = api_client.post(
        GENERATE,
        {
            "questions": [
                {"text": "What do you sell?", "workflow_target": "WF1"},
                {"text": "What makes you different?", "workflow_target": "WF2"},
            ]
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 400
    # Tightened by the weak-assertion sweep: this accepted WF3 appearing in
    # either field, so it would have passed if the endpoint stopped reporting
    # which workflow was missing. Both are part of the contract.
    body = response.json()
    assert body["missing_workflows"] == ["WF3"]
    assert "WF3" in body["error"]
    assert not Questionnaire.objects.exists(), "a set with no WF3 was stored"


def test_a_set_with_wf3_is_accepted(api_client, tenant):
    """The control — otherwise a rule that rejected everything would pass the
    test above."""
    assert generate(api_client, tenant).status_code == 201


def test_coverage_is_reported_as_three_fractions(api_client, tenant):
    """FR-PREP-08: "Coverage is reported as three fractions"."""
    coverage = generate(api_client, tenant).json()["coverage"]

    assert set(coverage) == {"WF1", "WF2", "WF3"}
    assert sum(coverage.values()) == pytest.approx(1.0)


# ── Validation at the boundary ───────────────────────────────────────


def test_a_write_without_the_token_is_refused(api_client):
    response = api_client.post(GENERATE, {"questions": questions()}, format="json")

    assert response.status_code == 403
    assert not Questionnaire.objects.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"questions": []},
        {"questions": "not-a-list"},
        {},
        {"questions": [{"text": "", "workflow_target": "WF1"}]},
        {"questions": [{"text": "A", "workflow_target": "WF9"}]},
        {"questions": ["not-an-object"]},
    ],
)
def test_a_malformed_set_is_refused(api_client, payload, tenant):
    response = api_client.post(
        GENERATE,
        payload,
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 400
    assert not Questionnaire.objects.exists()


def test_nothing_is_stored_when_validation_fails(api_client, tenant):
    """The write is atomic — a rejected set must not leave a childless
    questionnaire behind."""
    api_client.post(
        GENERATE,
        {"questions": [{"text": "A", "workflow_target": "WF1"}]},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert not Questionnaire.objects.exists()
    assert not Question.objects.exists()


# ── D2 · named depths onto B-01's 1-5 scale ──────────────────────────


@pytest.mark.parametrize(
    "given,expected", [("quick", 1), ("standard", 3), ("deep", 5), ("DEEP", 5)]
)
def test_a_named_depth_maps_to_the_stored_scale(api_client, given, expected, tenant):
    generate(api_client, tenant, depth=given)

    assert Questionnaire.objects.get().depth == expected


def test_a_numeric_depth_passes_through(api_client, tenant):
    """A programmatic caller says 4; the chat says "deep". Both are valid."""
    generate(api_client, tenant, depth=4)

    assert Questionnaire.objects.get().depth == 4


@pytest.mark.parametrize("given", ["nonsense", None, True, 99, -1, 0])
def test_an_unusable_depth_falls_back_to_standard(api_client, given, tenant):
    """Preparation with a slightly wrong research budget beats no preparation,
    and the operator can regenerate."""
    generate(api_client, tenant, depth=given)

    assert Questionnaire.objects.get().depth == DEPTH_NAMES["standard"]


def test_the_depth_names_are_inside_the_column_range():
    """B-01 documented the column as 1-5. A name mapping outside that range
    would fail at the database rather than here."""
    assert all(1 <= v <= 5 for v in DEPTH_NAMES.values())
    assert depth_from("standard") == DEPTH_NAMES["standard"]


# ── Reading it back ──────────────────────────────────────────────────


def test_a_viewer_can_read_a_questionnaire(api_client, tenant):
    user = User.objects.create_user("c03_viewer", "v@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.VIEWER)
    generate(api_client, tenant)

    api_client.force_authenticate(user=user)
    response = api_client.get("/api/v1/onboarding/questionnaires/")

    assert response.status_code == 200


def test_the_read_surface_nests_questions_in_order(api_client, tenant):
    user = User.objects.create_user("c03_read", "r@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.ADMIN)
    created = generate(api_client, tenant).json()

    api_client.force_authenticate(user=user)
    response = api_client.get(f"/api/v1/onboarding/questionnaires/{created['id']}/")

    assert response.status_code == 200, response.content
    assert [q["order"] for q in response.json()["questions"]] == [0, 1, 2]


# ── Tenant attribution through the endpoint ──────────────────────────


def test_the_questionnaire_is_attributed_to_the_header_tenant(api_client, tenant):
    """Not request.tenant, which DefaultTenantMiddleware resolves to the
    public tenant on any internal call."""
    generate(api_client, tenant)

    assert Questionnaire.objects.get().tenant == tenant


def test_a_write_without_the_tenant_header_is_refused(api_client):
    response = api_client.post(
        GENERATE,
        {"questions": questions()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
    )

    assert response.status_code == 400
    assert "X-Tenant-ID" in response.json()["error"]
    assert not Questionnaire.objects.exists()


# ── Review findings · the tenant is the authority for every lookup ───


def test_a_company_from_another_tenant_is_refused(api_client, tenant):
    """Review finding. Unscoped, a service-token caller could attach this
    questionnaire to another tenant's Company by guessing an id — the same
    class of cross-tenant defect this PR exists to fix, one field along.
    """
    other = Tenant.objects.create(name="Other", schema_name="c03_other")
    theirs = Company.objects.create(tenant=other, name="Not Yours")

    response = generate(api_client, tenant, company_id=theirs.pk)

    assert response.status_code == 400
    assert "does not belong to this tenant" in response.json()["error"]
    assert not Questionnaire.objects.exists()


def test_a_company_id_that_does_not_exist_is_refused(api_client, tenant):
    response = generate(api_client, tenant, company_id=999999)

    assert response.status_code == 400
    assert not Questionnaire.objects.exists()


def test_a_malformed_company_id_is_a_400_not_a_500(api_client, tenant):
    """The pk is a BigAutoField; a non-numeric value raises out of the
    queryset rather than returning nothing."""
    response = generate(api_client, tenant, company_id="not-a-number")

    assert response.status_code == 400


def test_a_session_from_another_tenant_is_ignored(api_client, tenant):
    """Strict scoping, not tenant_scope_q: that predicate admits tenant-less
    rows, which is right for a user's read and wrong for a service write
    handed an explicit tenant."""
    other = Tenant.objects.create(name="Other2", schema_name="c03_other2")
    company = Company.objects.create(tenant=other, name="Theirs")
    from apps.onboarding.models import OnboardingSession

    theirs = OnboardingSession.objects.create(tenant=other, company=company)

    response = generate(api_client, tenant, session_id=theirs.pk)

    assert response.status_code == 201
    assert (
        Questionnaire.objects.get().session is None
    ), "attached another tenant's session"


@pytest.mark.parametrize("bad", ["not-a-number", "", "1; DROP TABLE", "٣"])
def test_a_malformed_tenant_header_is_a_400_not_a_500(api_client, bad):
    """Review finding. A request boundary must not 500 on a malformed header
    from a caller that has otherwise authenticated correctly."""
    response = api_client.post(
        GENERATE,
        {"questions": questions()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=bad,
    )

    assert response.status_code == 400, response.content
    assert not Questionnaire.objects.exists()
