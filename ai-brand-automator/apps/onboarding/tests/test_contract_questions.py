"""Signed meeting records · step 1 — the mandatory contract-detail questions.

A signed record names two parties, so the details that identify the client
have to be collected. These tests cover the three promises that makes:

- every draft carries the fixed questions, first, on top of what was asked for;
- nobody can reword or drop one, and they leave on their own once answered;
- details that must be given in writing are never filled from a recording.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from hypothesis import given
from hypothesis import strategies as st
from rest_framework.test import APIClient

from apps.onboarding import contract_fields
from apps.onboarding.contract_fields import CONTRACT_FIELDS
from apps.onboarding.field_map import all_mapped_fields
from apps.onboarding.models import (
    ProvenanceStatus,
    Question,
    QuestionCategory,
    Questionnaire,
)
from apps.onboarding.tests.factories import make_provenance, make_session
from onboarding.models import Company
from tenants.models import Membership, Tenant

TOKEN = "dev-service-token"
GENERATE = "/api/v1/onboarding/questionnaires/generate/"
VOCABULARY = "/api/v1/onboarding/field-vocabulary/"
COMPANY_FIELDS = "/api/v1/onboarding/internal/companies/{pk}/fields/"

MANDATORY_FIELDS = [item.field for item in CONTRACT_FIELDS]

#: Everything a record needs, already given.
SETTLED = {
    "legal_name": "Kalyani Roasters Private Limited",
    "registered_address": "14 MG Road, Pune 411001",
    "signatory_name": "Asha Kalyani",
    "signatory_title": "Director",
    "signatory_email": "asha@example.com",
    "decision_maker": "Asha Kalyani",
    "billing_contact_email": "accounts@example.com",
    "registration_number": "U12345MH2020PTC000001",
}


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Contract Co", schema_name="contract_q")


@pytest.fixture
def editor(api_client, tenant):
    user = User.objects.create_user("cq_editor", "cqe@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.EDITOR)
    api_client.force_authenticate(user=user)
    return user


@pytest.fixture
def admin(api_client, tenant):
    user = User.objects.create_user("cq_admin", "cqa@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.ADMIN)
    api_client.force_authenticate(user=user)
    return user


def generated_set() -> list[dict]:
    return [
        {"text": "What do you sell?", "workflow_target": "WF1"},
        {"text": "What makes you different?", "workflow_target": "WF2"},
        {"text": "Do you have previous ads we can reuse?", "workflow_target": "WF3"},
    ]


def generate(api_client, tenant, **overrides):
    payload = {"questions": generated_set(), "depth": "standard"}
    payload.update(overrides)
    return api_client.post(
        GENERATE,
        payload,
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )


def mandatory_fields_on(questionnaire_id) -> list[str]:
    return list(
        Question.objects.filter(questionnaire_id=questionnaire_id, mandatory=True)
        .order_by("order")
        .values_list("target_field", flat=True)
    )


# ── The template itself ──────────────────────────────────────────────


@pytest.mark.unit
def test_every_template_field_exists_on_company():
    """A question whose answer has nowhere to go is a question asked for
    nothing."""
    company_fields = {f.name for f in Company._meta.get_fields()}
    assert set(MANDATORY_FIELDS) <= company_fields


@pytest.mark.unit
def test_every_template_field_is_in_the_review_vocabulary():
    """Otherwise the write boundary would blank its target_field."""
    assert set(MANDATORY_FIELDS) <= all_mapped_fields()


@pytest.mark.unit
def test_template_fields_and_questions_are_unique():
    assert len(set(MANDATORY_FIELDS)) == len(MANDATORY_FIELDS)
    texts = [item.question for item in CONTRACT_FIELDS]
    assert len(set(texts)) == len(texts)


@pytest.mark.unit
def test_what_a_record_cannot_be_issued_without():
    assert contract_fields.required_to_issue() == (
        "legal_name",
        "registered_address",
        "signatory_name",
        "signatory_title",
        "signatory_email",
    )


@pytest.mark.unit
def test_identifiers_and_email_addresses_are_written_only():
    """Speech-to-text is weakest on exactly these, and an identifier said
    aloud sits in the recording and every transcript tier."""
    assert contract_fields.written_only_fields() == {
        "signatory_email",
        "billing_contact_email",
        "registration_number",
    }


@pytest.mark.property
@given(st.text(alphabet=" \t\n\r\u00a0\u2003\u3000", max_size=20))
def test_whitespace_is_never_an_answer(blank):
    """A field holding only spaces would otherwise suppress its question for
    good."""
    assert contract_fields.is_answered(blank) is False


@pytest.mark.property
@given(st.text(min_size=1).filter(lambda t: t.strip()))
def test_any_real_text_is_an_answer(value):
    assert contract_fields.is_answered(value) is True


# ── Every draft carries them, first, on top of the count ─────────────


@pytest.mark.django_db
def test_a_new_draft_opens_with_every_contract_question_in_order(api_client, tenant):
    response = generate(api_client, tenant)

    assert response.status_code == 201, response.content
    body = response.json()
    head = body["questions"][: len(CONTRACT_FIELDS)]
    assert [q["target_field"] for q in head] == MANDATORY_FIELDS
    assert [q["text"] for q in head] == [item.question for item in CONTRACT_FIELDS]
    assert all(q["mandatory"] is True for q in head)
    assert all(q["category"] == QuestionCategory.CONTRACTUAL for q in head)


@pytest.mark.django_db
def test_they_are_in_addition_to_the_generated_set(api_client, tenant):
    """The operator asked for three questions about the brand and gets three
    — the contract questions do not eat into that."""
    body = generate(api_client, tenant).json()

    rest = body["questions"][len(CONTRACT_FIELDS) :]
    assert [q["text"] for q in rest] == [q["text"] for q in generated_set()]
    assert all(q["mandatory"] is False for q in rest)
    assert all(q["category"] == QuestionCategory.BRAND for q in rest)
    assert body["question_count"] == 3 + len(CONTRACT_FIELDS)
    assert body["questions_added"] == 3


@pytest.mark.django_db
def test_ordering_stays_contiguous(api_client, tenant):
    body = generate(api_client, tenant).json()

    assert [q["order"] for q in body["questions"]] == list(
        range(3 + len(CONTRACT_FIELDS))
    )


@pytest.mark.django_db
def test_a_second_turn_does_not_ask_them_twice(api_client, tenant):
    session = make_session(tenant=tenant)
    first = generate(api_client, tenant, session_id=str(session.pk)).json()

    generate(
        api_client,
        tenant,
        session_id=str(session.pk),
        questions=[
            {"text": "Who is your ideal customer?", "workflow_target": "WF1"},
            {"text": "Which ads worked before?", "workflow_target": "WF3"},
        ],
    )

    assert Questionnaire.objects.filter(session=session).count() == 1
    asked = mandatory_fields_on(first["id"])
    assert len(asked) == len(set(asked)), "a contract question was asked twice"
    assert asked == [
        f
        for f in MANDATORY_FIELDS
        if not contract_fields.is_answered(getattr(session.company, f))
    ]


# ── Only what is still missing is asked ──────────────────────────────


@pytest.mark.django_db
def test_a_detail_already_given_is_not_asked_again(api_client, tenant):
    company = Company.objects.create(
        tenant=tenant, name="Kalyani Roasters", legal_name=SETTLED["legal_name"]
    )

    body = generate(api_client, tenant, company_id=company.pk).json()

    assert mandatory_fields_on(body["id"]) == [
        f for f in MANDATORY_FIELDS if f != "legal_name"
    ]


@pytest.mark.django_db
def test_a_company_with_everything_settled_gets_no_contract_questions(
    api_client, tenant
):
    """The later-meeting case: nothing left to collect, nothing asked."""
    company = Company.objects.create(tenant=tenant, name="Kalyani Roasters", **SETTLED)

    body = generate(api_client, tenant, company_id=company.pk).json()

    assert mandatory_fields_on(body["id"]) == []
    assert body["question_count"] == 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [ProvenanceStatus.PENDING, ProvenanceStatus.CONFLICT]
)
def test_an_extracted_but_unreviewed_detail_is_still_asked(api_client, tenant, status):
    """What the agent heard is a guess about a legal name until someone
    confirms it. Asking once more is cheaper than signing a guess."""
    company = Company.objects.create(tenant=tenant, name="Kalyani Roasters", **SETTLED)
    session = make_session(company=company)
    make_provenance(session=session, field_name="legal_name", status=status)

    body = generate(api_client, tenant, session_id=str(session.pk)).json()

    assert mandatory_fields_on(body["id"]) == ["legal_name"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [ProvenanceStatus.CONFIRMED, ProvenanceStatus.EDITED]
)
def test_a_reviewed_detail_is_settled(api_client, tenant, status):
    company = Company.objects.create(tenant=tenant, name="Kalyani Roasters", **SETTLED)
    session = make_session(company=company)
    make_provenance(session=session, field_name="legal_name", status=status)

    body = generate(api_client, tenant, session_id=str(session.pk)).json()

    assert mandatory_fields_on(body["id"]) == []


@pytest.mark.django_db
def test_a_blank_value_does_not_count_as_given(api_client, tenant):
    company = Company.objects.create(
        tenant=tenant, name="Kalyani Roasters", **{**SETTLED, "signatory_name": "   "}
    )

    body = generate(api_client, tenant, company_id=company.pk).json()

    assert mandatory_fields_on(body["id"]) == ["signatory_name"]


# ── They cannot be reworded or dropped ───────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path, extra", [("rewrite", {"text": "Company name?"}), ("drop", {})]
)
def test_a_mandatory_question_cannot_be_changed(
    api_client, tenant, editor, path, extra
):
    qid = generate(api_client, tenant).json()["id"]
    question = Question.objects.filter(questionnaire_id=qid, mandatory=True).first()
    original = question.text

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/{path}/",
        {"question_id": question.pk, **extra},
        format="json",
    )

    assert response.status_code == 409, response.content
    assert "mandatory" in response.json()["error"]
    question.refresh_from_db()
    assert question.text == original


@pytest.mark.django_db
def test_an_ordinary_question_can_still_be_dropped(api_client, tenant, editor):
    qid = generate(api_client, tenant).json()["id"]
    question = Question.objects.filter(questionnaire_id=qid, mandatory=False).first()

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/drop/",
        {"question_id": question.pk},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert mandatory_fields_on(qid) == MANDATORY_FIELDS
    assert response.json()["question_count"] == 2 + len(CONTRACT_FIELDS)


# ── Later meetings ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_revising_for_a_later_meeting_drops_what_has_been_answered(
    api_client, tenant, admin
):
    company = Company.objects.create(tenant=tenant, name="Kalyani Roasters")
    qid = generate(api_client, tenant, company_id=company.pk).json()["id"]
    approved = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/approve/", format="json"
    )
    assert approved.status_code == 200, approved.content

    # The first meeting happened and these were confirmed.
    Company.objects.filter(pk=company.pk).update(
        legal_name=SETTLED["legal_name"],
        registered_address=SETTLED["registered_address"],
    )

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/revise/", format="json"
    )

    assert response.status_code == 201, response.content
    draft_id = response.json()["id"]
    assert mandatory_fields_on(draft_id) == [
        f for f in MANDATORY_FIELDS if f not in ("legal_name", "registered_address")
    ]
    # The approved version is the record of what was asked; it is untouched.
    assert mandatory_fields_on(qid) == MANDATORY_FIELDS


@pytest.mark.django_db
def test_a_clone_asks_for_the_new_companys_details_not_the_templates(
    api_client, tenant, editor
):
    """A template built for a client whose details were settled would
    otherwise hand the next client a questionnaire that asks for none."""
    settled = Company.objects.create(tenant=tenant, name="Settled Client", **SETTLED)
    qid = generate(api_client, tenant, company_id=settled.pk).json()["id"]
    assert mandatory_fields_on(qid) == []
    Questionnaire.objects.filter(pk=qid).update(is_template=True, company=None)
    settled.delete()
    newcomer = Company.objects.create(tenant=tenant, name="New Client")

    response = api_client.post(
        f"/api/v1/onboarding/questionnaires/{qid}/clone/",
        {"company_id": newcomer.pk},
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert mandatory_fields_on(body["id"]) == MANDATORY_FIELDS
    assert body["question_count"] == 3 + len(CONTRACT_FIELDS)


# ── What the generator is told ───────────────────────────────────────


@pytest.mark.django_db
def test_the_vocabulary_says_what_the_contract_questions_cover(api_client, tenant):
    response = api_client.get(
        VOCABULARY, HTTP_X_SERVICE_TOKEN=TOKEN, HTTP_X_TENANT_ID=str(tenant.pk)
    )

    assert response.status_code == 200, response.content
    covered = response.json()["covered"]
    assert [c["field"] for c in covered] == MANDATORY_FIELDS
    assert all(c["topic"] for c in covered)
    # The existing contract is unchanged: a plain list of field names.
    assert set(MANDATORY_FIELDS) <= set(response.json()["fields"])


# ── Written-only details never come from a recording ─────────────────


@pytest.mark.django_db
def test_extraction_cannot_write_a_written_only_detail(api_client, tenant):
    """The agent is not given these as targets. This is the backstop: a
    misheard address must never become where signing links are sent."""
    company = Company.objects.create(tenant=tenant, name="Kalyani Roasters")

    response = api_client.patch(
        COMPANY_FIELDS.format(pk=company.pk),
        {
            "signatory_name": "Asha Kalyani",
            "signatory_email": "asha@exampel.com",
            "billing_contact_email": "accounts@exampel.com",
            "registration_number": "U12345",
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 200, response.content
    assert response.json()["fields_written"] == ["signatory_name"]
    company.refresh_from_db()
    assert company.signatory_name == "Asha Kalyani"
    assert company.signatory_email is None
    assert company.billing_contact_email is None
    assert company.registration_number is None


@pytest.mark.django_db
def test_the_spoken_details_can_be_extracted(api_client, tenant):
    company = Company.objects.create(tenant=tenant, name="Kalyani Roasters")

    response = api_client.patch(
        COMPANY_FIELDS.format(pk=company.pk),
        {
            "legal_name": SETTLED["legal_name"],
            "registered_address": SETTLED["registered_address"],
            "signatory_name": SETTLED["signatory_name"],
            "signatory_title": SETTLED["signatory_title"],
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 200, response.content
    company.refresh_from_db()
    assert company.registered_address == SETTLED["registered_address"]
    assert company.signatory_title == SETTLED["signatory_title"]


# ── They do not distort workflow coverage ────────────────────────────


@pytest.mark.django_db
def test_contract_questions_are_left_out_of_workflow_coverage(api_client, tenant):
    """They carry a workflow only because the column needs one. Counted, the
    eight of them would drag discovery coverage down to a ninth."""
    body = generate(api_client, tenant).json()
    Question.objects.filter(
        questionnaire_id=body["id"], mandatory=False, workflow_target="WF1"
    ).update(status="GREEN", sufficiency_score=0.9, evidence=[{"recording_id": 1}])

    questionnaire = Questionnaire.objects.get(pk=body["id"])
    from apps.onboarding.serializers import QuestionnaireSerializer

    coverage = QuestionnaireSerializer(questionnaire).data["coverage"]

    assert coverage["WF1"] == 1.0
