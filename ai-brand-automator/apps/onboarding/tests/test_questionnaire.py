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
from django.db import DatabaseError, transaction
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


# ── C-04 AC-2 · approved questions are frozen, in the database ───────


@pytest.fixture
def approved(api_client, tenant):
    """A questionnaire moved to APPROVED, with its questions in place."""
    created = generate(api_client, tenant).json()
    row = Questionnaire.objects.get(pk=created["id"])
    row.status = QuestionnaireStatus.APPROVED
    row.save()
    return row


def test_approval_freezes_version(approved):
    """The card's named case.

    Enforced by a PostgreSQL trigger rather than a save() guard, and the
    parametrisation below is why: update() and bulk_update() skip save() and
    every signal hanging off it, and both are the natural way to renumber a
    set of questions. B-05 made the same call for the same reason.
    """
    question = Question.objects.filter(questionnaire=approved).first()
    question.text = "edited after approval"

    with pytest.raises(DatabaseError), transaction.atomic():
        question.save()

    question.refresh_from_db()
    assert question.text != "edited after approval"


@pytest.mark.parametrize("path", ["update", "bulk_update", "insert"])
def test_every_write_path_to_an_approved_set_is_blocked(approved, path):
    """The paths a Python guard would miss.

    ``save()`` is the one people remember. These four are the ones that make a
    model-level check a hole rather than a rule.
    """
    rows = list(Question.objects.filter(questionnaire=approved))

    def act():
        if path == "update":
            Question.objects.filter(questionnaire=approved).update(text="x")
        elif path == "bulk_update":
            rows[0].text = "x"
            Question.objects.bulk_update(rows, ["text"])
        else:
            Question.objects.create(
                questionnaire=approved,
                order=99,
                text="sneaked in?",
                origin=QuestionOrigin.PREPARED,
                workflow_target="WF1",
                target_field="",
                status=QuestionStatus.OPEN,
            )

    with pytest.raises(DatabaseError), transaction.atomic():
        act()

    assert Question.objects.filter(questionnaire=approved).count() == len(rows)


def test_a_draft_is_still_editable(api_client, tenant):
    """The control. A trigger that froze everything would pass the tests above
    while making refinement impossible — which is the rest of this story."""
    created = generate(api_client, tenant).json()
    question = Question.objects.filter(questionnaire_id=created["id"]).first()

    question.text = "edited while draft"
    question.save()

    question.refresh_from_db()
    assert question.text == "edited while draft"


def test_deleting_the_questionnaire_still_cascades(approved):
    """A cascade is not an edit. Blocking it would make an approved
    questionnaire undeletable, which GDPR erasure (M-02) needs."""
    approved.delete()

    assert not Question.objects.filter(questionnaire_id=approved.pk).exists()


def test_the_questionnaire_row_itself_can_still_change(approved):
    """Approving is an UPDATE on Questionnaire, and superseding writes to it
    again. Freezing the parent would block the very transition that sets
    APPROVED."""
    approved.is_template = True
    approved.save()

    approved.refresh_from_db()
    assert approved.is_template is True


def test_deleting_a_question_is_not_blocked_by_the_database(approved):
    """A stated limit, not an oversight — recorded so nobody assumes otherwise.

    The trigger covers INSERT and UPDATE, which are the paths an edit takes.
    DELETE is not covered because no formulation of the check can tell an
    individual delete apart from the cascade that M-02's erasure depends on:
    Django removes children before the parent, so the parent still exists and
    still reads APPROVED at the moment each child goes.

    Refusing it is the service layer's job — see the refine endpoints, which
    create a new version rather than touching an approved one. This test
    exists so the gap is visible in the suite rather than only in a migration
    docstring.
    """
    Question.objects.filter(questionnaire=approved).delete()

    assert not Question.objects.filter(questionnaire=approved).exists()


# ── C-04 AC-1 · refinement keeps ordering contiguous ─────────────────


@pytest.fixture
def editor(api_client, tenant):
    user = User.objects.create_user("c04_editor", "e@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.EDITOR)
    api_client.force_authenticate(user=user)
    return user


@pytest.fixture
def admin(api_client, tenant):
    user = User.objects.create_user("c04_admin", "a@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.ADMIN)
    api_client.force_authenticate(user=user)
    return user


def a_draft(api_client, tenant) -> int:
    """A stored DRAFT, created through the agent's endpoint."""
    return generate(api_client, tenant).json()["id"]


def orders(questionnaire_id) -> list[int]:
    return list(
        Question.objects.filter(questionnaire_id=questionnaire_id)
        .order_by("order")
        .values_list("order", flat=True)
    )


def test_rewrite_replaces_one_question(api_client, tenant):
    qid = a_draft(api_client, tenant)
    question = Question.objects.filter(questionnaire_id=qid).first()
    editor_user = User.objects.create_user("rw", "rw@t.com", "TestPass123!")
    Membership.objects.create(
        user=editor_user, tenant=tenant, role=Membership.Role.EDITOR
    )
    api_client.force_authenticate(user=editor_user)

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/rewrite/",
        {"question_id": question.pk, "text": "What is your average order value?"},
        format="json",
    )

    assert response.status_code == 200, response.content
    question.refresh_from_db()
    assert question.text == "What is your average order value?"


def test_dropping_a_question_closes_the_gap(api_client, tenant):
    """AC-1: "leaves ordering contiguous". A hole would put the meeting view
    out of step with the numbers the operator says out loud."""
    qid = a_draft(api_client, tenant)
    middle = Question.objects.filter(questionnaire_id=qid).order_by("order")[1]
    user = User.objects.create_user("dr", "dr@t.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.EDITOR)
    api_client.force_authenticate(user=user)

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/drop/",
        {"question_id": middle.pk},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert orders(qid) == [0, 1]
    assert Questionnaire.objects.get(pk=qid).question_count == 2


def test_reorder_requires_every_question_exactly_once(api_client, tenant):
    """A partial list would leave the rest in an order nobody chose."""
    qid = a_draft(api_client, tenant)
    ids = list(
        Question.objects.filter(questionnaire_id=qid).values_list("id", flat=True)
    )
    user = User.objects.create_user("ro", "ro@t.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.EDITOR)
    api_client.force_authenticate(user=user)

    partial = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/reorder/",
        {"question_ids": ids[:2]},
        format="json",
    )
    assert partial.status_code == 400

    full = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/reorder/",
        {"question_ids": list(reversed(ids))},
        format="json",
    )

    assert full.status_code == 200, full.content
    assert orders(qid) == [0, 1, 2]
    reordered = list(
        Question.objects.filter(questionnaire_id=qid)
        .order_by("order")
        .values_list("id", flat=True)
    )
    assert reordered == list(reversed(ids))


def test_refining_an_approved_set_is_refused_with_advice(api_client, tenant, admin):
    """The service-layer half of AC-2, and the delete gap the trigger leaves.

    Refusing here rather than letting the trigger fire gives the operator the
    useful answer — revise it — instead of an integrity error.
    """
    qid = a_draft(api_client, tenant)
    api_client.post(f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json")
    question = Question.objects.filter(questionnaire_id=qid).first()

    for path, payload in (
        ("rewrite", {"question_id": question.pk, "text": "x?"}),
        ("drop", {"question_id": question.pk}),
        ("reorder", {"question_ids": [question.pk]}),
    ):
        response = api_client.post(
            f"/api/v1/onboarding/questionnaires/{qid}/{path}/", payload, format="json"
        )
        assert response.status_code == 409, (path, response.content)
        assert "revise" in response.json()["detail"]

    assert Question.objects.filter(questionnaire_id=qid).count() == 3


# ── C-04 AC-2 · approval ─────────────────────────────────────────────


def test_approval_sets_the_audit_fields(api_client, tenant, admin):
    qid = a_draft(api_client, tenant)

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json"
    )

    assert response.status_code == 200, response.content
    row = Questionnaire.objects.get(pk=qid)
    assert row.status == QuestionnaireStatus.APPROVED
    assert row.approved_by == admin
    assert row.approved_at is not None


def test_approval_moves_the_session_to_ready(api_client, tenant, admin):
    """AC-2's second half, through B-04's table rather than by assignment."""
    from apps.onboarding.models import OnboardingSession, SessionStatus

    company = Company.objects.create(tenant=tenant, name="Kalyani")
    session = OnboardingSession.objects.create(
        tenant=tenant, company=company, status=SessionStatus.PREPARING
    )
    qid = a_draft(api_client, tenant)
    Questionnaire.objects.filter(pk=qid).update(session=session)

    api_client.post(f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json")

    session.refresh_from_db()
    assert session.status == SessionStatus.READY


def test_an_empty_questionnaire_cannot_be_approved(api_client, tenant, admin):
    """Approving nothing would gate a meeting on a set with no questions."""
    qid = a_draft(api_client, tenant)
    Question.objects.filter(questionnaire_id=qid).delete()

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json"
    )

    assert response.status_code == 400
    assert Questionnaire.objects.get(pk=qid).status == QuestionnaireStatus.DRAFT


def test_an_editor_cannot_approve(api_client, tenant, editor):
    """§15 has no row for approval, so this follows the card's "As an Admin"
    and CONFIRM_KEY_FIELD's precedent that a decision needs ADMIN."""
    qid = a_draft(api_client, tenant)

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json"
    )

    assert response.status_code == 403
    assert Questionnaire.objects.get(pk=qid).status == QuestionnaireStatus.DRAFT


# ── C-04 AC-3 · revision creates a version ───────────────────────────


def test_reapproval_creates_new_version(api_client, tenant, admin):
    """The card's named case. The approved version must survive intact — the
    evidence spans on Question point at a specific version's rows."""
    qid = a_draft(api_client, tenant)
    api_client.post(f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json")
    before = list(
        Question.objects.filter(questionnaire_id=qid)
        .order_by("order")
        .values_list("text", flat=True)
    )

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/revise/", format="json"
    )

    assert response.status_code == 201, response.content
    draft = Questionnaire.objects.get(pk=response.json()["id"])
    assert draft.version == 2
    assert draft.status == QuestionnaireStatus.DRAFT
    assert draft.supersedes_id == qid

    approved = Questionnaire.objects.get(pk=qid)
    assert approved.status == QuestionnaireStatus.APPROVED
    after = list(
        Question.objects.filter(questionnaire_id=qid)
        .order_by("order")
        .values_list("text", flat=True)
    )
    assert after == before, "the approved version changed"


def test_editing_the_new_draft_leaves_the_approved_one_alone(api_client, tenant, admin):
    """FR-PREP-05: the approved version stays byte-identical."""
    qid = a_draft(api_client, tenant)
    api_client.post(f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json")
    draft_id = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/revise/", format="json"
    ).json()["id"]
    target = Question.objects.filter(questionnaire_id=draft_id).first()

    api_client.post(
        f"/api/v1/onboarding/questionnaires/{draft_id}/rewrite/",
        {"question_id": target.pk, "text": "changed in v2?"},
        format="json",
    )

    assert not Question.objects.filter(
        questionnaire_id=qid, text="changed in v2?"
    ).exists()


def test_a_version_cannot_be_revised_twice(api_client, tenant, admin):
    """Two operators revising the same approved set would otherwise both open
    version 2. The row lock serialises them; this is the second one's answer."""
    qid = a_draft(api_client, tenant)
    api_client.post(f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json")
    api_client.post(f"/api/v1/onboarding/questionnaires/{qid}/revise/", format="json")

    second = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/revise/", format="json"
    )

    assert second.status_code == 409
    assert Questionnaire.objects.filter(supersedes_id=qid).count() == 1


def test_a_draft_cannot_be_revised(api_client, tenant, admin):
    qid = a_draft(api_client, tenant)

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/revise/", format="json"
    )

    assert response.status_code == 409


# ── D-05 · template reuse ────────────────────────────────────────────


def test_a_template_can_be_cloned_for_another_company(api_client, tenant, editor):
    qid = a_draft(api_client, tenant)
    Questionnaire.objects.filter(pk=qid).update(is_template=True)
    other = Company.objects.create(tenant=tenant, name="Second Client")

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/clone/",
        {"company_id": other.pk},
        format="json",
    )

    assert response.status_code == 201, response.content
    clone = Questionnaire.objects.get(pk=response.json()["id"])
    assert clone.company == other
    assert clone.version == 1
    assert clone.status == QuestionnaireStatus.DRAFT
    assert clone.questions.count() == 3


def test_a_non_template_cannot_be_cloned(api_client, tenant, editor):
    """Cloning an arbitrary questionnaire would put one company's prepared
    questions under another's name with no record of where they came from."""
    qid = a_draft(api_client, tenant)
    other = Company.objects.create(tenant=tenant, name="Third Client")

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/clone/",
        {"company_id": other.pk},
        format="json",
    )

    assert response.status_code == 409


def test_a_template_cannot_be_cloned_onto_another_tenants_company(
    api_client, tenant, editor
):
    qid = a_draft(api_client, tenant)
    Questionnaire.objects.filter(pk=qid).update(is_template=True)
    outsider = Tenant.objects.create(name="Outsider", schema_name="c04_outsider")
    theirs = Company.objects.create(tenant=outsider, name="Not Yours")

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/clone/",
        {"company_id": theirs.pk},
        format="json",
    )

    assert response.status_code == 400
    assert not Questionnaire.objects.filter(company=theirs).exists()
