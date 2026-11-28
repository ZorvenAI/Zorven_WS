"""Erasure review queue: deciding requests held for signed meeting records.

Real database, real cascade. ``erase anyway`` queues a Celery task; these
tests run Celery eagerly, so the real task and the real cascade run in-process
when the decision commits.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from hypothesis import HealthCheck, given
from hypothesis import settings as hsettings
from hypothesis import strategies as st
from rest_framework.test import APIClient

from apps.onboarding.erasure import review
from apps.onboarding.erasure.cascade import ErasureCascade
from apps.onboarding.erasure.models import ErasureLog, RetentionConfig, ReviewStatus
from apps.onboarding.erasure.registry import StoreRegistry
from apps.onboarding.models import ConsentRecord, OnboardingSession, SessionStatus
from apps.onboarding.records.models import MeetingRecord, RecordEvent, RecordEventType
from apps.onboarding.tests.factories import make_recording
from tenants.models import Membership

User = get_user_model()
BASE = "/api/v1/onboarding/erasure/review"
SUBJECT = "Maria Rossi"
REASON = "Signed agreement may be needed for a dispute."


@pytest.fixture(autouse=True)
def _stores():
    from apps.onboarding.erasure.stores.django_brand_assets import (
        DjangoBrandAssetStore,
    )
    from apps.onboarding.erasure.stores.django_sessions import DjangoSessionStore
    from apps.onboarding.erasure.stores.gcs_blobs import GCSBlobStore
    from apps.onboarding.erasure.stores.oia_redis import OIARedisStore
    from apps.onboarding.erasure.stores.poi_golden_datasets import POIGoldenStore
    from apps.onboarding.erasure.stores.rag_index_store import RAGIndexStore

    StoreRegistry.reset()
    for cls in (
        DjangoBrandAssetStore,
        DjangoSessionStore,
        GCSBlobStore,
        OIARedisStore,
        POIGoldenStore,
        RAGIndexStore,
    ):
        StoreRegistry.register(cls)
    yield
    StoreRegistry.reset()


@pytest.fixture(autouse=True)
def _public_tenant(db):
    """The public tenant and ``localhost`` domain the tenant middleware needs.

    ``conftest.setup_public_tenant`` creates them once per session, but a
    ``transaction=True`` test truncates every table when it ends, so the next
    request in this file found no tenant at all. Recreated here, the same way.
    """
    from tenants.models import Domain, Tenant

    public, _ = Tenant.objects.get_or_create(
        schema_name="public",
        defaults={"name": "Public Test Tenant", "subscription_status": "active"},
    )
    Domain.objects.get_or_create(
        domain="localhost", defaults={"tenant": public, "is_primary": True}
    )


@pytest.fixture(autouse=True)
def _eager_celery():
    from brand_automator.celery import app

    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = False
    yield
    app.conf.task_always_eager = False


@pytest.fixture
def company(db, tenant):
    from onboarding.models import Company

    return Company.objects.create(tenant=tenant, name="Pomodoro")


def _client(tenant, role, username):
    user = User.objects.create_user(username, f"{username}@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=role)
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return client, user


@pytest.fixture
def admin(tenant):
    return _client(tenant, Membership.Role.ADMIN, "rq_admin")


def _session(tenant, company, *, signed: bool, number: str = "MR-RQ-1"):
    session = OnboardingSession.objects.create(
        tenant=tenant, company=company, status=SessionStatus.COMPLETED
    )
    ConsentRecord.objects.create(
        tenant=tenant, session=session, subject_name=SUBJECT, granted_at=timezone.now()
    )
    if signed:
        record = MeetingRecord.objects.create(
            tenant=tenant,
            session=session,
            recording=make_recording(session=session, tenant=tenant),
            record_number=number,
            status="COMPLETED",
            content_hash="ab" * 32,
            issued_at=timezone.now(),
            completed_at=timezone.now(),
        )
        RecordEvent.objects.create(
            tenant=tenant, record=record, event_type=RecordEventType.ISSUED
        )
    return session


def _held_request(tenant, company, **kw) -> tuple[ErasureLog, OnboardingSession]:
    """An erasure request run through the real cascade, which holds it."""
    session = _session(tenant, company, signed=True, **kw)
    log = ErasureLog.objects.create(tenant=tenant, subject_name=SUBJECT)
    report = ErasureCascade().execute(tenant_id=str(tenant.pk), subject_name=SUBJECT)
    log.completion_report = report.to_dict()
    log.completed_at = timezone.now()
    log.review_status = ReviewStatus.PENDING
    log.save()
    return log, session


# ── The queue ────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_a_held_request_is_listed_with_what_it_holds(admin, tenant, company):
    log, session = _held_request(tenant, company)
    client, _ = admin

    body = client.get(f"{BASE}/").json()

    assert [r["id"] for r in body] == [log.pk]
    assert body[0]["subject_name"] == SUBJECT
    assert body[0]["held"] == [
        {
            "session_id": str(session.pk),
            "company_name": "Pomodoro",
            "records": [{"record_number": "MR-RQ-1", "status": "COMPLETED"}],
        }
    ]
    assert body[0]["overdue"] is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("days,overdue", [(24, False), (25, True), (26, True)])
def test_a_request_is_overdue_from_day_25(admin, tenant, company, days, overdue):
    log, _ = _held_request(tenant, company)
    ErasureLog.objects.filter(pk=log.pk).update(
        requested_at=timezone.now() - timedelta(days=days, minutes=1)
    )
    client, _ = admin

    row = client.get(f"{BASE}/").json()[0]

    assert row["days_waiting"] == days
    assert row["overdue"] is overdue


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("role", [Membership.Role.EDITOR, Membership.Role.VIEWER])
def test_only_owners_and_admins_see_or_decide(tenant, company, role):
    log, _ = _held_request(tenant, company)
    client, _ = _client(tenant, role, f"rq_{role}")

    assert client.get(f"{BASE}/").status_code == 403
    keep = client.post(f"{BASE}/{log.pk}/keep/", {"reason": REASON}, format="json")
    assert keep.status_code == 403
    assert ErasureLog.objects.get(pk=log.pk).review_status == ReviewStatus.PENDING


@pytest.mark.django_db(transaction=True)
def test_another_workspaces_request_is_not_found(admin, tenant, company):
    from tenants.models import Tenant

    other = Tenant.objects.create(name="Other", schema_name="rq_other")
    foreign = ErasureLog.objects.create(
        tenant=other, subject_name=SUBJECT, review_status=ReviewStatus.PENDING
    )
    client, _ = admin

    assert client.get(f"{BASE}/").json() == []
    resp = client.post(f"{BASE}/{foreign.pk}/keep/", {"reason": REASON}, format="json")
    assert resp.status_code == 404


# ── Keep ─────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_keeping_holds_the_sessions_until_the_default_date(admin, tenant, company):
    log, session = _held_request(tenant, company)
    RetentionConfig.objects.create(tenant=tenant, legal_hold_years=3)
    client, user = admin

    resp = client.post(f"{BASE}/{log.pk}/keep/", {"reason": REASON}, format="json")

    assert resp.status_code == 200, resp.content
    log.refresh_from_db()
    today = timezone.localdate()
    assert log.review_status == ReviewStatus.KEPT
    assert log.hold_until == today.replace(year=today.year + 3)
    assert log.reviewed_by == user
    assert log.review_reason == REASON
    assert OnboardingSession.objects.filter(pk=session.pk).exists()
    assert client.get(f"{BASE}/").json() == []
    assert [r["id"] for r in client.get(f"{BASE}/?status=KEPT").json()] == [log.pk]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("reason", ["", "   ", "too short"])
def test_a_decision_needs_a_real_reason(admin, tenant, company, reason):
    log, _ = _held_request(tenant, company)
    client, _ = admin

    resp = client.post(f"{BASE}/{log.pk}/keep/", {"reason": reason}, format="json")

    assert resp.status_code == 400
    assert resp.json()["error"] == "reason_required"
    assert ErasureLog.objects.get(pk=log.pk).review_status == ReviewStatus.PENDING


@pytest.mark.django_db(transaction=True)
def test_a_hold_must_end_in_the_future(admin, tenant, company):
    log, _ = _held_request(tenant, company)
    client, _ = admin

    resp = client.post(
        f"{BASE}/{log.pk}/keep/",
        {"reason": REASON, "hold_until": timezone.localdate().isoformat()},
        format="json",
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "hold_until_past"


@pytest.mark.django_db(transaction=True)
def test_a_decided_request_cannot_be_decided_again(admin, tenant, company):
    log, _ = _held_request(tenant, company)
    client, _ = admin
    client.post(f"{BASE}/{log.pk}/keep/", {"reason": REASON}, format="json")

    again = client.post(
        f"{BASE}/{log.pk}/erase/",
        {"reason": REASON, "confirm_subject": SUBJECT},
        format="json",
    )

    assert again.status_code == 409
    assert ErasureLog.objects.get(pk=log.pk).review_status == ReviewStatus.KEPT


@pytest.mark.django_db(transaction=True)
def test_two_reviewers_at_once_only_one_decides(tenant, company):
    """The row lock: exactly one of two simultaneous decisions lands."""
    log, _ = _held_request(tenant, company)
    _, alice = _client(tenant, Membership.Role.ADMIN, "rq_alice")
    _, bob = _client(tenant, Membership.Role.ADMIN, "rq_bob")
    outcomes: list[str] = []
    start = threading.Barrier(2)

    def decide(user):
        start.wait()
        try:
            review.keep(log, user=user, reason=REASON)
            outcomes.append("kept")
        except review.ReviewError as exc:
            outcomes.append(exc.code)
        finally:
            connection.close()

    threads = [threading.Thread(target=decide, args=(u,)) for u in (alice, bob)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == ["kept", "not_pending"]


# ── Erase anyway ─────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_erasing_needs_the_subjects_name_typed_exactly(admin, tenant, company):
    log, session = _held_request(tenant, company)
    client, _ = admin

    resp = client.post(
        f"{BASE}/{log.pk}/erase/",
        {"reason": REASON, "confirm_subject": "maria rossi"},
        format="json",
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "confirmation_mismatch"
    assert OnboardingSession.objects.filter(pk=session.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_erasing_anyway_removes_the_held_session_and_leaves_a_tombstone(
    admin, tenant, company
):
    log, session = _held_request(tenant, company)
    client, user = admin

    resp = client.post(
        f"{BASE}/{log.pk}/erase/",
        {"reason": REASON, "confirm_subject": SUBJECT},
        format="json",
    )

    assert resp.status_code == 202, resp.content
    log.refresh_from_db()
    assert log.review_status == ReviewStatus.ERASED
    assert log.reviewed_by == user
    assert not OnboardingSession.objects.filter(pk=session.pk).exists()
    assert not MeetingRecord.objects.filter(record_number="MR-RQ-1").exists()
    assert not RecordEvent.objects.filter(record__record_number="MR-RQ-1").exists()
    tombstone = log.completion_report["review_erase"]["erased_signed_records"]
    assert [
        (t["record_number"], t["status"], t["content_hash"]) for t in tombstone
    ] == [("MR-RQ-1", "COMPLETED", "ab" * 32)]
    assert SUBJECT not in str(tombstone)
    # The first run's report, with what was held, is kept alongside.
    assert log.completion_report["held_for_review"][0]["session_id"] == str(session.pk)


# ── Retention ────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_an_expired_hold_returns_to_the_queue(tenant, company):
    from apps.onboarding.erasure.tasks import _awaiting_review

    log, _ = _held_request(tenant, company)
    ErasureLog.objects.filter(pk=log.pk).update(
        review_status=ReviewStatus.KEPT,
        hold_until=timezone.localdate() - timedelta(days=1),
    )

    assert _awaiting_review(tenant, SUBJECT) is True
    assert ErasureLog.objects.get(pk=log.pk).review_status == ReviewStatus.PENDING


@pytest.mark.django_db(transaction=True)
def test_an_in_date_hold_is_skipped_and_stays_kept(tenant, company):
    from apps.onboarding.erasure.tasks import _awaiting_review

    log, _ = _held_request(tenant, company)
    ErasureLog.objects.filter(pk=log.pk).update(
        review_status=ReviewStatus.KEPT,
        hold_until=timezone.localdate() + timedelta(days=30),
    )

    assert _awaiting_review(tenant, SUBJECT) is True
    assert ErasureLog.objects.get(pk=log.pk).review_status == ReviewStatus.KEPT


@pytest.mark.django_db(transaction=True)
def test_the_cascade_task_queues_a_held_request_for_review(tenant, company):
    from apps.onboarding.erasure.tasks import execute_erasure_cascade

    _session(tenant, company, signed=True)
    log = ErasureLog.objects.create(tenant=tenant, subject_name=SUBJECT)

    execute_erasure_cascade.apply(
        kwargs={
            "tenant_id": str(tenant.pk),
            "subject_name": SUBJECT,
            "erasure_log_id": log.pk,
        }
    )

    assert ErasureLog.objects.get(pk=log.pk).review_status == ReviewStatus.PENDING


# ── Hold period setting ──────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("years,code", [(0, 400), (26, 400), (10, 200)])
def test_the_hold_period_is_one_to_twenty_five_years(admin, years, code):
    client, _ = admin

    resp = client.patch(
        "/api/v1/onboarding/retention/", {"legal_hold_years": years}, format="json"
    )

    assert resp.status_code == code
    if code == 200:
        current = client.get("/api/v1/onboarding/retention/").json()
        assert current["legal_hold_years"] == years


# ── Property: what a run erases ──────────────────────────────────────


@pytest.mark.django_db(transaction=True)
@hsettings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(signed=st.lists(st.booleans(), min_size=1, max_size=4))
def test_a_run_erases_exactly_the_unheld_sessions_unless_forced(
    tenant, company, signed
):
    stamp = timezone.now().strftime("%H%M%S%f")
    sessions = [
        _session(tenant, company, signed=flag, number=f"MR-P-{stamp}-{i}")
        for i, flag in enumerate(signed)
    ]
    ids = [s.pk for s in sessions]
    held = {s.pk for s, flag in zip(sessions, signed) if flag}

    ErasureCascade().execute(tenant_id=str(tenant.pk), subject_name=SUBJECT)
    remaining = set(
        OnboardingSession.objects.filter(pk__in=ids).values_list("pk", flat=True)
    )
    assert remaining == held

    ErasureCascade().execute(
        tenant_id=str(tenant.pk), subject_name=SUBJECT, force_session_ids=held
    )
    assert not OnboardingSession.objects.filter(pk__in=ids).exists()


# ── A queued erase must still be the decision that stands ────────────


def _forced_run(log, session, token):
    from apps.onboarding.erasure.tasks import execute_erasure_cascade

    return execute_erasure_cascade.apply(
        kwargs={
            "tenant_id": str(log.tenant_id),
            "subject_name": SUBJECT,
            "erasure_log_id": log.pk,
            "force_session_ids": [str(session.pk)],
            "decision_token": token,
        }
    ).result


@pytest.mark.django_db(transaction=True)
def test_a_stale_erase_does_nothing_once_the_request_was_kept(tenant, company):
    """An erase queued earlier must not run over a later decision to keep."""
    log, session = _held_request(tenant, company)
    _, user = _client(tenant, Membership.Role.ADMIN, "rq_keeper")
    stale_token = timezone.now().isoformat()
    review.keep(log, user=user, reason=REASON)

    result = _forced_run(log, session, stale_token)

    assert result == {"skipped": "decision_no_longer_current"}
    assert OnboardingSession.objects.filter(pk=session.pk).exists()
    assert ErasureLog.objects.get(pk=log.pk).review_status == ReviewStatus.KEPT


@pytest.mark.django_db(transaction=True)
def test_an_erase_without_its_decision_does_nothing(tenant, company):
    """A forced run whose decision was cleared (after a failure) or replaced
    by another one is refused, so nothing erases without a standing decision."""
    log, session = _held_request(tenant, company)

    assert _forced_run(log, session, None) == {"skipped": "decision_no_longer_current"}
    assert _forced_run(log, session, timezone.now().isoformat()) == {
        "skipped": "decision_no_longer_current"
    }
    assert OnboardingSession.objects.filter(pk=session.pk).exists()
    assert ErasureLog.objects.get(pk=log.pk).review_status == ReviewStatus.PENDING
