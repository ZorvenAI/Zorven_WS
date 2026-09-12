"""D-03 · pushing in-app meetings outward, and reconciling (AC-2, AC-4).

The card names `test_conflict_resolution_rule`.

The stub here is a *stateful* calendar, not a queue of canned replies: it
stores what is inserted, applies patches, honours deletes and serves the result
back on the next list. That is what makes the round-trip tests real — "create
in the app, sync twice, and there is exactly one event on either side" is a
claim about a calendar that remembers, and a replay-based stub cannot make it.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.integrations import sync
from apps.integrations.models import CalendarConnection, ConnectionStatus
from apps.onboarding.models import (
    CalendarSyncConflict,
    ConflictWinner,
    MeetingOrigin,
    MeetingStatus,
    OnboardingSession,
    ScheduledMeeting,
)
from onboarding.models import Company
from tenants.models import Tenant

pytestmark = pytest.mark.django_db


class FakeCalendar:
    """Enough of a Google calendar to be worth syncing against."""

    def __init__(self):
        self.events: dict[str, dict] = {}
        self.deleted: dict[str, dict] = {}
        self.counter = 0
        self.write_status = 200
        self.calls: list[tuple[str, str]] = []

    def insert(self, body: dict) -> dict:
        self.counter += 1
        event_id = f"g-{self.counter}"
        stored = dict(body)
        stored["id"] = event_id
        stored["status"] = "confirmed"
        stored["updated"] = timezone.now().isoformat().replace("+00:00", "Z")
        self.events[event_id] = stored
        return stored

    def patch(self, event_id: str, body: dict) -> dict | None:
        stored = self.events.get(event_id)
        if stored is None:
            return None
        stored.update(body)
        stored["updated"] = timezone.now().isoformat().replace("+00:00", "Z")
        return stored

    def delete(self, event_id: str) -> bool:
        stored = self.events.pop(event_id, None)
        if stored is None:
            return False
        self.deleted[event_id] = {"id": event_id, "status": "cancelled"}
        return True

    def listing(self, incremental: bool) -> dict:
        items = list(self.events.values())
        if incremental:
            # Deletions only ever surface on an incremental read.
            items = items + list(self.deleted.values())
        return {"items": items, "nextSyncToken": f"tok-{self.counter}-{len(items)}"}

    def edit_externally(self, event_id: str, **changes) -> None:
        """Somebody changing the event in Google, between syncs."""
        self.events[event_id].update(changes)
        self.events[event_id]["updated"] = (
            timezone.now().isoformat().replace("+00:00", "Z")
        )


@pytest.fixture
def calendar():
    state = FakeCalendar()

    class Handler(BaseHTTPRequestHandler):
        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                return json.loads(raw or b"{}")
            except ValueError:
                return {}

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path.endswith("/events"):
                state.calls.append(("insert", ""))
                if state.write_status != 200:
                    return self._reply(state.write_status, {"error": {"message": "no"}})
                return self._reply(200, state.insert(body))
            # Anything else on POST is the OAuth token endpoint.
            return self._reply(200, {"access_token": "access-token-abc"})

        def do_PATCH(self):
            event_id = urlparse(self.path).path.rsplit("/", 1)[-1]
            body = self._body()
            state.calls.append(("patch", event_id))
            if state.write_status != 200:
                return self._reply(state.write_status, {"error": {"message": "no"}})
            updated = state.patch(event_id, body)
            if updated is None:
                return self._reply(404, {"error": {"message": "Not Found"}})
            return self._reply(200, updated)

        def do_DELETE(self):
            event_id = urlparse(self.path).path.rsplit("/", 1)[-1]
            state.calls.append(("delete", event_id))
            if state.write_status != 200:
                return self._reply(state.write_status, {"error": {"message": "no"}})
            if not state.delete(event_id):
                return self._reply(404, {"error": {"message": "Not Found"}})
            return self._reply(204, None)

        def do_GET(self):
            params = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            state.calls.append(("list", params.get("syncToken", "")))
            return self._reply(200, state.listing(bool(params.get("syncToken"))))

        def _reply(self, status, body):
            payload = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload:
                self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = f"http://127.0.0.1:{server.server_address[1]}"

    previous = {
        key: os.environ.get(key)
        for key in (
            "GOOGLE_OAUTH_BASE",
            "GOOGLE_CALENDAR_API_BASE",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "CALENDAR_SYNC_NAMESPACE",
        )
    }
    os.environ["GOOGLE_OAUTH_BASE"] = root
    os.environ["GOOGLE_CALENDAR_API_BASE"] = f"{root}/calendar"
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["CALENDAR_SYNC_NAMESPACE"] = "zorven-test"
    try:
        yield state
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        server.shutdown()
        server.server_close()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="D03 Push", schema_name="d03_push")


@pytest.fixture
def organiser():
    return User.objects.create_user("d03_org", "organiser@test.com", "TestPass123!")


@pytest.fixture
def session(tenant):
    company = Company.objects.create(tenant=tenant, name="Kalyani Roasters")
    return OnboardingSession.objects.create(tenant=tenant, company=company)


@pytest.fixture
def connection(tenant):
    conn = CalendarConnection.objects.create(
        tenant=tenant, status=ConnectionStatus.CONNECTED
    )
    conn.refresh_token = "refresh-abc"
    conn.save()
    return conn


def a_meeting(tenant, session, organiser, *, title="Onboarding call", **extra):
    start = timezone.now() + timedelta(days=1)
    return ScheduledMeeting.objects.create(
        tenant=tenant,
        session=session,
        organiser=organiser,
        starts_at=start,
        ends_at=start + timedelta(minutes=60),
        timezone="Europe/London",
        title=title,
        **extra,
    )


def writes(calendar, kind):
    return [c for c in calendar.calls if c[0] == kind]


# ── AC-2 · in-app meetings are pushed outward ────────────────────────


def test_a_new_meeting_reaches_google(connection, tenant, session, organiser, calendar):
    meeting = a_meeting(tenant, session, organiser)

    sync.pull_connection(connection)

    assert len(calendar.events) == 1
    event = next(iter(calendar.events.values()))
    assert event["summary"] == "Onboarding call"
    meeting.refresh_from_db()
    assert meeting.provider_event_id == event["id"]


def test_the_pushed_event_carries_the_instant_and_the_attendee(
    connection, tenant, session, organiser, calendar
):
    """AC-2: "the same instant, title and attendees".

    Attendees is the thin part, and deliberately so: nothing in this system
    records who a meeting is *with*, so the organiser is the only participant
    with an address. Flagged in the PR rather than papered over.
    """
    meeting = a_meeting(tenant, session, organiser)

    sync.pull_connection(connection)

    event = next(iter(calendar.events.values()))
    assert event["start"]["timeZone"] == "Europe/London"
    assert event["start"]["dateTime"].startswith(
        meeting.starts_at.isoformat()[:16].replace("+00:00", "")
    )
    assert event["attendees"] == [{"email": "organiser@test.com"}]


def test_an_edit_updates_rather_than_duplicates(
    connection, tenant, session, organiser, calendar
):
    """AC-2's second half, named in the criterion: "subsequent edits update
    rather than duplicate it"."""
    meeting = a_meeting(tenant, session, organiser)
    sync.pull_connection(connection)

    meeting.title = "Onboarding call (rescheduled)"
    meeting.save()
    sync.pull_connection(connection)

    assert len(calendar.events) == 1
    assert next(iter(calendar.events.values()))["summary"] == (
        "Onboarding call (rescheduled)"
    )
    assert len(writes(calendar, "insert")) == 1
    assert len(writes(calendar, "patch")) == 1


def test_an_unchanged_meeting_is_not_pushed_again(
    connection, tenant, session, organiser, calendar
):
    """The quota question, and the reason provider_synced_at is written with
    update() rather than save(): save() bumps `updated_at`, every meeting looks
    permanently dirty, and the sweep patches the entire calendar every three
    minutes forever."""
    a_meeting(tenant, session, organiser)
    sync.pull_connection(connection)

    sync.pull_connection(connection)
    sync.pull_connection(connection)

    assert len(writes(calendar, "insert")) == 1
    assert writes(calendar, "patch") == []


def test_a_cancelled_meeting_is_removed_from_google(
    connection, tenant, session, organiser, calendar
):
    meeting = a_meeting(tenant, session, organiser)
    sync.pull_connection(connection)

    meeting.status = MeetingStatus.CANCELLED
    meeting.save()
    sync.pull_connection(connection)

    assert calendar.events == {}
    assert len(writes(calendar, "delete")) == 1


def test_a_meeting_cancelled_before_it_was_pushed_is_left_alone(
    connection, tenant, session, organiser, calendar
):
    """And is not reconsidered forever: an unpushed cancellation with no
    provider event is nothing to send, but it must stop being a candidate."""
    a_meeting(tenant, session, organiser, status=MeetingStatus.CANCELLED)

    sync.pull_connection(connection)
    sync.pull_connection(connection)

    assert calendar.events == {}
    assert writes(calendar, "insert") == []


def test_an_external_meeting_is_never_pushed(connection, tenant, calendar):
    """Mirrors are not ours to write back. Pushing one would create a second
    copy of the operator's own appointment in their own calendar."""
    start = timezone.now() + timedelta(days=1)
    ScheduledMeeting.objects.create(
        tenant=tenant,
        session=None,
        starts_at=start,
        ends_at=start + timedelta(minutes=30),
        timezone="Europe/London",
        origin=MeetingOrigin.GOOGLE,
        provider_event_id="g-external",
        title="Dentist",
    )

    sync.pull_connection(connection)

    assert writes(calendar, "insert") == []
    assert writes(calendar, "patch") == []


# ── FR-CAL-03 · no duplicate on *either* side ────────────────────────


def test_a_round_trip_creates_no_duplicate_on_either_side(
    connection, tenant, session, organiser, calendar
):
    """The requirement's own verification, end to end.

    The meeting goes out, comes back on the next incremental read carrying our
    tag, and must not become a second in-app meeting — nor a second Google
    event.
    """
    a_meeting(tenant, session, organiser)

    sync.pull_connection(connection)
    sync.pull_connection(connection)
    sync.pull_connection(connection)

    assert ScheduledMeeting.objects.count() == 1
    assert len(calendar.events) == 1


# ── AC-4 · conflicts have a documented resolution ────────────────────


def test_conflict_resolution_rule(connection, tenant, session, organiser, calendar):
    """The card's named case.

    "In-app wins for onboarding-owned events; Google wins for externally
    created ones", and "the losing change is recorded rather than discarded
    silently". Both halves are asserted: the surviving value, and the row that
    says what did not survive.
    """
    meeting = a_meeting(tenant, session, organiser, title="Onboarding call")
    sync.pull_connection(connection)
    event_id = next(iter(calendar.events))

    # Somebody edits our meeting in Google, between syncs.
    calendar.edit_externally(event_id, summary="Hijacked in Google")
    sync.pull_connection(connection)

    # In-app won: the Google copy carries our title again.
    assert calendar.events[event_id]["summary"] == "Onboarding call"
    meeting.refresh_from_db()
    assert meeting.title == "Onboarding call"

    # And the losing change was recorded, not dropped.
    conflict = CalendarSyncConflict.objects.get()
    assert conflict.winner == ConflictWinner.APP
    assert conflict.discarded["summary"] == "Hijacked in Google"
    assert conflict.meeting_id == meeting.pk
    assert conflict.rule


def test_google_wins_for_an_externally_created_event(connection, tenant, calendar):
    """The rule's other half. An external event edited in Google simply
    updates here — this app is not its system of record, and the read-only
    guard means there is no in-app edit to lose."""
    calendar.insert(
        {
            "summary": "Dentist",
            "start": {
                "dateTime": (timezone.now() + timedelta(days=1))
                .isoformat()
                .replace("+00:00", "Z"),
                "timeZone": "Europe/London",
            },
            "end": {
                "dateTime": (timezone.now() + timedelta(days=1, minutes=30))
                .isoformat()
                .replace("+00:00", "Z"),
                "timeZone": "Europe/London",
            },
        }
    )
    sync.pull_connection(connection)

    calendar.edit_externally("g-1", summary="Dentist (moved)")
    sync.pull_connection(connection)

    assert ScheduledMeeting.objects.count() == 1
    assert ScheduledMeeting.objects.get().title == "Dentist (moved)"
    assert not CalendarSyncConflict.objects.exists()


def test_an_unchanged_owned_event_is_not_a_conflict(
    connection, tenant, session, organiser, calendar
):
    """The control, and the reason comparison is by value rather than by
    timestamp. Google's `updated` moves when *we* write, so a timestamp check
    would report a conflict on every push — and record our own change as the
    losing one."""
    a_meeting(tenant, session, organiser)

    sync.pull_connection(connection)
    sync.pull_connection(connection)
    sync.pull_connection(connection)

    assert not CalendarSyncConflict.objects.exists()


def test_a_meeting_deleted_in_google_comes_back(
    connection, tenant, session, organiser, calendar
):
    """In-app wins, so deleting an onboarding meeting in Google does not
    cancel it here — it is recreated, and the deletion is recorded."""
    meeting = a_meeting(tenant, session, organiser)
    sync.pull_connection(connection)
    event_id = next(iter(calendar.events))

    calendar.delete(event_id)
    sync.pull_connection(connection)

    meeting.refresh_from_db()
    assert meeting.status == MeetingStatus.SCHEDULED
    assert meeting.provider_event_id and meeting.provider_event_id != event_id
    assert len(calendar.events) == 1
    conflict = CalendarSyncConflict.objects.get()
    assert conflict.winner == ConflictWinner.APP
    assert conflict.discarded["status"] == "cancelled"


# ── AC-3 · push failures are survivable too ──────────────────────────


def test_a_failed_push_does_not_lose_the_meeting(
    connection, tenant, session, organiser, calendar
):
    """It stays dirty and is retried, rather than being marked synced and
    never sent."""
    a_meeting(tenant, session, organiser)
    calendar.write_status = 500

    sync.pull_connection(connection)

    assert ScheduledMeeting.objects.get().provider_event_id == ""
    calendar.write_status = 200
    sync.pull_connection(connection)
    assert len(calendar.events) == 1


def test_one_failed_push_does_not_stop_the_others(
    connection, tenant, session, organiser, calendar
):
    """A push loop that died on the first failure would leave every later
    meeting unsent, and looking sent to nobody in particular.

    Driven through push_connection directly rather than a whole cycle: a
    tenant may hold only one Company, and therefore one active session and one
    scheduled meeting, so two *pushable* meetings means one scheduled and one
    cancelled — a rescheduled session, which is the ordinary way that pair
    arises.
    """
    doomed = a_meeting(tenant, session, organiser, title="Patch me")
    ScheduledMeeting.objects.filter(pk=doomed.pk).update(
        provider_event_id="g-missing", provider_synced_at=None
    )
    live = calendar.insert({"summary": "Old slot"})
    cancelled = ScheduledMeeting.objects.create(
        tenant=tenant,
        session=session,
        organiser=organiser,
        starts_at=timezone.now() + timedelta(days=3),
        ends_at=timezone.now() + timedelta(days=3, minutes=30),
        timezone="Europe/London",
        status=MeetingStatus.CANCELLED,
        title="Old slot",
    )
    ScheduledMeeting.objects.filter(pk=cancelled.pk).update(
        provider_event_id=live["id"]
    )

    counts = sync.push_connection(connection, "access-token-abc")

    # The patch against an event Google does not have fails; the delete of the
    # one it does have still happens.
    assert counts["failed"] == 1
    assert counts["deleted"] == 1
    assert live["id"] not in calendar.events


def test_deleting_an_event_google_has_already_forgotten_is_success(
    connection, tenant, session, organiser, calendar
):
    """The goal state is "no event", and it is already reached. Failing here
    would strand the cancellation in a permanent retry."""
    meeting = a_meeting(tenant, session, organiser)
    sync.pull_connection(connection)
    event_id = next(iter(calendar.events))
    calendar.events.pop(event_id)

    meeting.status = MeetingStatus.CANCELLED
    meeting.save()
    result = sync.pull_connection(connection)

    assert result["failed"] == 0
    meeting.refresh_from_db()
    assert meeting.provider_synced_at is not None


def test_another_tenants_tagged_event_is_not_reconciled_as_ours(
    connection, tenant, calendar
):
    """Where #570's tenant check meets this PR's reconciliation.

    Two tenants can connect the same Google account. Before the tenant part of
    the tag was checked, tenant A's tagged event read during tenant B's sync
    counted as B's own — which under this PR is worse than a skip: it would
    reach `reconcile_owned`, and a mismatch against a meeting B does not have
    is exactly the shape that records a conflict. B would accumulate conflict
    rows about A's meetings.

    From B's side it is an ordinary external event, and that is what it becomes.
    """
    other = Tenant.objects.create(name="Other tenant", schema_name="d03_push_other")
    start = timezone.now() + timedelta(days=1)
    calendar.insert(
        {
            "summary": "Their onboarding call",
            "start": {
                "dateTime": start.isoformat().replace("+00:00", "Z"),
                "timeZone": "Europe/London",
            },
            "end": {
                "dateTime": (start + timedelta(minutes=30))
                .isoformat()
                .replace("+00:00", "Z"),
                "timeZone": "Europe/London",
            },
            "extendedProperties": {
                "private": {sync.TAG_KEY: f"zorven-test:{other.pk}:99"}
            },
        }
    )

    sync.pull_connection(connection)

    mirrored = ScheduledMeeting.objects.get()
    assert mirrored.origin == MeetingOrigin.GOOGLE
    assert mirrored.tenant_id == tenant.pk
    assert not CalendarSyncConflict.objects.exists()
