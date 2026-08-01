"""B-01 model tests (AC-1, AC-2, AC-4).

The two named cases from the card — ``test_one_active_session_per_company``
and ``test_question_score_and_evidence_atomic`` — are the ones that matter:
they prove the invariants are properties of the database and the model rather
than of a serializer a later caller might bypass.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.onboarding.models import (
    TERMINAL_STATUSES,
    OnboardingSession,
    Question,
    Questionnaire,
    QuestionnaireStatus,
    QuestionOrigin,
    QuestionStatus,
    SessionStatus,
    WorkflowTarget,
)
from apps.onboarding.tests.factories import (
    evidence_span,
    make_company,
    make_question,
    make_questionnaire,
    make_session,
)

pytestmark = pytest.mark.django_db


# ── AC-2 · one live session per company, in the database ─────────────


def test_one_active_session_per_company():
    """A second non-terminal session fails on the partial unique index."""
    company = make_company()
    make_session(company=company, status=SessionStatus.DRAFT)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_session(company=company, status=SessionStatus.PREPARING)


@pytest.mark.parametrize("terminal", [s.value for s in TERMINAL_STATUSES])
def test_a_second_session_is_allowed_once_the_first_is_terminal(terminal):
    """AC-2's other half: the constraint releases on COMPLETED or ARCHIVED."""
    company = make_company()
    first = make_session(company=company, status=SessionStatus.MEETING_LIVE)

    first.status = terminal
    first.save(update_fields=["status"])

    second = make_session(company=company, status=SessionStatus.DRAFT)
    assert second.pk != first.pk
    assert OnboardingSession.objects.filter(company=company).count() == 2


def test_two_companies_may_each_hold_an_active_session():
    """The constraint is per company, not global."""
    make_session(company=make_company(name="A"), status=SessionStatus.DRAFT)
    make_session(company=make_company(name="B"), status=SessionStatus.DRAFT)
    assert OnboardingSession.objects.count() == 2


@pytest.mark.parametrize(
    "status",
    [s.value for s in SessionStatus if s not in TERMINAL_STATUSES],
)
def test_every_non_terminal_status_blocks_a_second_session(status):
    """No status outside the terminal set is a loophole."""
    company = make_company()
    make_session(company=company, status=status)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_session(company=company, status=SessionStatus.DRAFT)


# ── AC-1 · the models match Design §10.1 ─────────────────────────────


def test_session_carries_every_designed_field():
    session = make_session()
    for field in (
        "tenant",
        "company",
        "status",
        "escalated_from",
        "questionnaire",
        "created_by",
        "prompt_versions",
        "evidence_manifest_hash",
        "created_at",
        "updated_at",
    ):
        assert hasattr(session, field), field


def test_session_statuses_are_the_state_machine_set():
    """§9.4 verbatim, plus ARCHIVED, which AC-2's terminal set requires."""
    assert {s.value for s in SessionStatus} == {
        "DRAFT",
        "PREPARING",
        "READY",
        "MEETING_LIVE",
        "GATHERED",
        "PROCESSING",
        "REVIEW_PENDING",
        "CONFIRMED",
        "COMPLETED",
        "ESCALATED",
        "ARCHIVED",
    }
    assert set(TERMINAL_STATUSES) == {SessionStatus.COMPLETED, SessionStatus.ARCHIVED}


def test_escalated_from_remembers_the_prior_status():
    """§9.4: without it, resolution would have to guess."""
    session = make_session(status=SessionStatus.GATHERED)
    session.escalated_from = session.status
    session.status = SessionStatus.ESCALATED
    session.save(update_fields=["status", "escalated_from"])

    session.refresh_from_db()
    assert session.escalated_from == SessionStatus.GATHERED
    assert session.is_terminal is False


def test_questionnaire_carries_every_designed_field():
    questionnaire = make_questionnaire()
    for field in (
        "tenant",
        "company",
        "session",
        "status",
        "depth",
        "question_count",
        "source_chat_session_id",
        "approved_by",
        "approved_at",
        "version",
        "is_template",
    ):
        assert hasattr(questionnaire, field), field
    assert questionnaire.status == QuestionnaireStatus.DRAFT
    assert questionnaire.version == 1


def test_question_carries_every_designed_field():
    question = make_question()
    for field in (
        "questionnaire",
        "order",
        "text",
        "origin",
        "workflow_target",
        "target_field",
        "status",
        "sufficiency_score",
        "answer_summary",
        "evidence",
    ):
        assert hasattr(question, field), field
    assert question.origin == QuestionOrigin.PREPARED
    assert question.workflow_target == WorkflowTarget.WF1
    assert question.status == QuestionStatus.OPEN


# ── OG-06 · score and evidence are atomic ────────────────────────────


def test_question_score_and_evidence_atomic():
    """A score without evidence is refused — it is an unsourced claim."""
    questionnaire = make_questionnaire()

    with pytest.raises(ValidationError) as exc:
        make_question(questionnaire=questionnaire, sufficiency_score=0.86)
    assert "evidence" in exc.value.message_dict


def test_evidence_without_a_score_is_also_refused():
    """The rule is both-or-neither, not score-implies-evidence."""
    questionnaire = make_questionnaire()

    with pytest.raises(ValidationError) as exc:
        make_question(questionnaire=questionnaire, evidence=[evidence_span()])
    assert "sufficiency_score" in exc.value.message_dict


def test_score_with_evidence_is_accepted():
    """The negative tests mean nothing unless the happy path works."""
    question = make_question(
        sufficiency_score=0.86,
        evidence=[evidence_span()],
        status=QuestionStatus.GREEN,
    )
    question.refresh_from_db()
    assert question.sufficiency_score == 0.86
    assert question.evidence[0]["recording_id"] == "r_01"


def test_neither_score_nor_evidence_is_the_default_and_is_valid():
    question = make_question()
    assert question.sufficiency_score is None
    assert question.evidence == []


def test_the_rule_survives_an_update_not_just_a_create():
    """A later story updating a row must not be able to bypass it."""
    question = make_question()
    question.sufficiency_score = 0.91

    with pytest.raises(ValidationError):
        question.save()


# ── Tenant scoping ───────────────────────────────────────────────────


def test_for_tenant_excludes_other_tenants(public_tenant):
    """The manager filter is the ORM-layer guard the technical note demands."""
    mine = make_session(tenant=public_tenant)
    theirs = make_session(tenant=None)

    scoped = OnboardingSession.objects.for_tenant(public_tenant)
    assert mine in scoped
    # Pre-tenant rows stay visible; that is the fleet's compatibility pattern.
    assert theirs in scoped

    from tenants.models import Tenant

    other = Tenant.objects.create(name="Other", schema_name="other_tenant")
    other_session = make_session(tenant=other)
    assert other_session not in OnboardingSession.objects.for_tenant(public_tenant)


def test_for_tenant_with_none_returns_only_untenanted_rows(public_tenant):
    tenanted = make_session(tenant=public_tenant)
    untenanted = make_session(tenant=None)

    scoped = OnboardingSession.objects.for_tenant(None)
    assert untenanted in scoped
    assert tenanted not in scoped


# ── Representation and ordering ──────────────────────────────────────


def test_str_is_readable():
    session = make_session()
    assert str(session.pk) in str(session)
    assert session.status in str(session)
    assert "Questionnaire" in str(make_questionnaire())
    assert "Q1" in str(make_question(order=1))


def test_questions_order_within_a_questionnaire():
    questionnaire = make_questionnaire()
    make_question(questionnaire=questionnaire, order=2, text="second")
    make_question(questionnaire=questionnaire, order=1, text="first")

    assert [q.order for q in Question.objects.filter(questionnaire=questionnaire)] == [
        1,
        2,
    ]


def test_questionnaire_approval_fields_default_empty():
    questionnaire = make_questionnaire()
    assert questionnaire.approved_by is None
    assert questionnaire.approved_at is None
    assert questionnaire.is_template is False


def test_session_prompt_versions_defaults_to_an_empty_dict():
    """L-03 writes it; B-01 only guarantees the column and a safe default."""
    assert make_session().prompt_versions == {}
    assert Questionnaire.objects.count() == 0
