"""D-03 · pulling Google Calendar into the in-app calendar.

The card names `test_sync_failure_non_fatal` and `test_conflict_resolution_rule`;
the second belongs to the outbound half and lands with it.

No mocks. One local HTTP server stands in for both Google endpoints this needs
— the OAuth token endpoint and the Calendar API — so `refresh`, `list_events`,
pagination, 410 handling and every parse in between run for real. Tests drive
it by queueing the exact responses Google would send, which is the only way to
exercise a page loop or an expired cursor at all.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.integrations import sync
from apps.integrations.models import CalendarConnection, ConnectionStatus
from apps.onboarding.models import (
    MeetingOrigin,
    MeetingStatus,
    OnboardingSession,
    ScheduledMeeting,
)
from onboarding.models import Company
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

SYNC_NOW = "/api/v1/integrations/google-calendar/sync/"
EVENTS = "/api/v1/onboarding/calendar/events/"


def an_event(event_id: str, *, start=None, minutes=30, summary="Dentist", **extra):
    """A Google event as Google actually sends one."""
    start = start or (timezone.now() + timedelta(days=1))
    payload = {
        "id": event_id,
        "summary": summary,
        "status": "confirmed",
        "updated": start.isoformat().replace("+00:00", "Z"),
        "start": {
            "dateTime": start.isoformat().replace("+00:00", "Z"),
            "timeZone": "Europe/London",
        },
        "end": {
            "dateTime": (start + timedelta(minutes=minutes))
            .isoformat()
            .replace("+00:00", "Z"),
            "timeZone": "Europe/London",
        },
    }
    payload.update(extra)
    return payload


def a_page(events, *, sync_token="tok-1", next_page=""):
    body = {"items": events}
    if next_page:
        body["nextPageToken"] = next_page
    else:
        body["nextSyncToken"] = sync_token
    return 200, body


@pytest.fixture
def google():
    """Google's token endpoint and Calendar API, on one local server.

    `responses` is a queue of (status, body) served in order to events.list, so
    a test can compose a page loop or an expired cursor precisely. `requests`
    records what arrived, which is how the incremental-sync tests prove a sync
    token was actually *sent* rather than merely stored.
    """
    state = {"responses": [], "requests": [], "token_status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self._reply(
                state["token_status"],
                (
                    {"access_token": "access-token-abc"}
                    if state["token_status"] == 200
                    else {"error": "invalid_grant"}
                ),
            )

        def do_GET(self):
            parsed = urlparse(self.path)
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            state["requests"].append({"path": parsed.path, "params": params})
            if state["responses"]:
                status, body = state["responses"].pop(0)
            else:
                status, body = 200, {"items": [], "nextSyncToken": "tok-empty"}
            self._reply(status, body)

        def _reply(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
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
    return Tenant.objects.create(name="D03 Co", schema_name="d03_sync")


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


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


def member(api_client, tenant, role, username):
    user = User.objects.create_user(username, f"{username}@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=role)
    api_client.force_authenticate(user=user)
    return user


@pytest.fixture
def editor(api_client, tenant):
    return member(api_client, tenant, Membership.Role.EDITOR, "d03_editor")


def event_calls(google):
    return [r for r in google["requests"] if r["path"].endswith("/events")]


# ── AC-1 · external events appear ────────────────────────────────────


def test_an_external_event_becomes_a_visible_meeting(connection, google):
    google["responses"] = [a_page([an_event("evt-1", summary="Board review")])]

    counts = sync.pull_connection(connection)

    assert counts["created"] == 1
    meeting = ScheduledMeeting.objects.get()
    assert meeting.origin == MeetingOrigin.GOOGLE
    assert meeting.provider_event_id == "evt-1"
    assert meeting.title == "Board review"
    # No onboarding session, and that is the point — somebody's own diary entry
    # is not an onboarding meeting.
    assert meeting.session_id is None
    assert meeting.tenant_id == connection.tenant_id


def test_the_zone_survives_rather_than_the_offset(connection, google):
    """D-01 stores an IANA zone precisely so a meeting survives a DST change.
    Flattening external events to an offset would put them back on the footing
    that decision was made to avoid — and the column would refuse them."""
    google["responses"] = [a_page([an_event("evt-1")])]

    sync.pull_connection(connection)

    assert ScheduledMeeting.objects.get().timezone == "Europe/London"


# ── FR-CAL-03 · no duplicates ────────────────────────────────────────


def test_syncing_twice_creates_no_duplicate(connection, google):
    """FR-CAL-03's verification, named in the requirement: "a round-trip
    creates no duplicate on either side when sync runs twice, keyed on the
    provider event ID"."""
    event = an_event("evt-1")
    google["responses"] = [a_page([event]), a_page([event], sync_token="tok-2")]

    sync.pull_connection(connection)
    sync.pull_connection(connection)

    assert ScheduledMeeting.objects.filter(provider_event_id="evt-1").count() == 1


def test_the_database_refuses_a_duplicate_even_if_the_loop_would_allow_one(
    connection, tenant, google
):
    """Idempotence held only by get_or_create is idempotence until two cycles
    overlap — a slow sweep and a manual refresh are enough. The constraint is
    what makes it true regardless."""
    from django.db import IntegrityError
    from django.db import transaction as db_transaction

    google["responses"] = [a_page([an_event("evt-1")])]
    sync.pull_connection(connection)

    with pytest.raises(IntegrityError):
        with db_transaction.atomic():
            ScheduledMeeting.objects.create(
                tenant=tenant,
                session=None,
                starts_at=timezone.now(),
                ends_at=timezone.now() + timedelta(minutes=30),
                timezone="UTC",
                provider_event_id="evt-1",
                origin=MeetingOrigin.GOOGLE,
            )


def test_meetings_without_a_provider_event_do_not_collide(connection, tenant, session):
    """The partial condition earns its keep: every unpushed meeting carries the
    empty string, and a plain unique would allow exactly one of them."""
    for _ in range(3):
        ScheduledMeeting.objects.create(
            tenant=tenant,
            session=None,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(minutes=30),
            timezone="UTC",
        )

    assert ScheduledMeeting.objects.filter(provider_event_id="").count() == 3


# ── Incremental reads ────────────────────────────────────────────────


def test_the_sync_token_is_stored_and_then_sent(connection, google):
    """The card: "use a sync token rather than polling a date range; full
    re-fetch on every cycle will hit quota with a handful of tenants"."""
    google["responses"] = [
        a_page([an_event("evt-1")], sync_token="tok-A"),
        a_page([], sync_token="tok-B"),
    ]

    sync.pull_connection(connection)
    connection.refresh_from_db()
    assert connection.sync_token == "tok-A"

    sync.pull_connection(connection)

    calls = event_calls(google)
    assert "syncToken" not in calls[0]["params"], "the first read must be a full one"
    assert calls[1]["params"]["syncToken"] == "tok-A"
    # Google rejects a request carrying both a cursor and a window.
    assert "timeMin" not in calls[1]["params"]


def test_the_sync_token_comes_only_from_the_final_page(connection, google):
    """Taking one from an earlier page acknowledges changes we have not read.
    The next incremental sync would start after them and they would be lost —
    silently, and permanently."""
    google["responses"] = [
        (200, {"items": [an_event("evt-1")], "nextPageToken": "page-2"}),
        a_page([an_event("evt-2")], sync_token="tok-final"),
    ]

    counts = sync.pull_connection(connection)

    assert counts["created"] == 2
    connection.refresh_from_db()
    assert connection.sync_token == "tok-final"


def test_an_expired_cursor_falls_back_to_a_full_read(connection, google):
    """Google expires sync tokens on its own schedule. Keeping a dead one means
    every future cycle 410s and sync stops for good — silently, because nobody
    is paged about a 410."""
    connection.sync_token = "stale-token"
    connection.save()
    google["responses"] = [
        (410, {"error": {"message": "Sync token is no longer valid"}}),
        a_page([an_event("evt-1")], sync_token="tok-fresh"),
    ]

    counts = sync.pull_connection(connection)

    assert counts["created"] == 1
    connection.refresh_from_db()
    assert connection.sync_token == "tok-fresh"
    # The retry must be a genuine full read, not the dead cursor sent again.
    assert "syncToken" not in event_calls(google)[1]["params"]


def test_a_remote_cancellation_cancels_the_mirror(connection, google):
    """Deletions only ever arrive on an incremental read, as `status:
    cancelled`. A date-range poll would never show them, and the meeting would
    sit on the pane forever."""
    google["responses"] = [
        a_page([an_event("evt-1")]),
        a_page([{"id": "evt-1", "status": "cancelled"}], sync_token="tok-2"),
    ]
    sync.pull_connection(connection)

    counts = sync.pull_connection(connection)

    assert counts["cancelled"] == 1
    # Cancelled, not deleted — D-01's rule that the record survives.
    assert ScheduledMeeting.objects.get().status == MeetingStatus.CANCELLED


# ── Ownership · AC-4's precondition ──────────────────────────────────


def test_an_event_we_created_is_not_mirrored_back(connection, google):
    """The tag is what makes AC-4 decidable rather than heuristic. Without it
    the outbound half's own event returns on the next pull and becomes a second
    meeting — the duplicate FR-CAL-03 forbids, arriving by the other door."""
    tagged = an_event(
        "evt-ours",
        extendedProperties={"private": {sync.TAG_KEY: "zorven-test:1:42"}},
    )
    google["responses"] = [a_page([tagged])]

    counts = sync.pull_connection(connection)

    assert counts["created"] == 0
    assert not ScheduledMeeting.objects.exists()


def test_another_deployments_tag_is_not_ours(connection, google):
    """Google's "private" extended properties are private to the calendar, not
    to the app: staging and production reading the same operator's calendar see
    each other's tags. Without the namespace, staging would silently disown a
    production meeting."""
    foreign = an_event(
        "evt-theirs",
        extendedProperties={"private": {sync.TAG_KEY: "someone-else:1:42"}},
    )
    google["responses"] = [a_page([foreign])]

    counts = sync.pull_connection(connection)

    assert counts["created"] == 1
    assert ScheduledMeeting.objects.get().origin == MeetingOrigin.GOOGLE


def test_an_untagged_app_meeting_is_not_seized(connection, tenant, session, google):
    """An operator can strip extended properties, and some clients do it for
    them. Rewriting the row to GOOGLE would hand ownership to the other side
    and invert AC-4 for that meeting — in-app would stop winning, with nothing
    to show why."""
    ScheduledMeeting.objects.create(
        tenant=tenant,
        session=session,
        starts_at=timezone.now() + timedelta(days=1),
        ends_at=timezone.now() + timedelta(days=1, minutes=30),
        timezone="Europe/London",
        provider_event_id="evt-app",
        origin=MeetingOrigin.APP,
        title="Onboarding call",
    )
    google["responses"] = [a_page([an_event("evt-app", summary="Renamed in Google")])]

    counts = sync.pull_connection(connection)

    assert counts["skipped"] == 1
    meeting = ScheduledMeeting.objects.get()
    assert meeting.origin == MeetingOrigin.APP
    assert meeting.title == "Onboarding call"


# ── AC-3 · sync failure is never fatal ───────────────────────────────


def test_sync_failure_non_fatal(
    connection, tenant, session, google, api_client, editor
):
    """The card's named case.

    "The in-app calendar continues to function fully" is the claim, so it is
    the claim under test: the pane is read *after* the failure and must still
    answer with the tenant's own meetings.
    """
    ScheduledMeeting.objects.create(
        tenant=tenant,
        session=session,
        starts_at=timezone.now() + timedelta(days=1),
        ends_at=timezone.now() + timedelta(days=1, minutes=30),
        timezone="Europe/London",
        title="Onboarding call",
    )
    google["responses"] = [(500, {"error": {"message": "backend error"}})]

    result = sync.pull_connection(connection)

    assert "error" in result
    listed = api_client.get(EVENTS).json()
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert [row["title"] for row in rows] == ["Onboarding call"]


def test_a_failure_is_recorded_and_backed_off(connection, google):
    google["responses"] = [(503, {"error": {"message": "unavailable"}})]

    sync.pull_connection(connection)

    connection.refresh_from_db()
    assert connection.sync_failures == 1
    assert connection.last_sync_error
    assert connection.sync_backoff_until > timezone.now()


def test_the_backoff_grows_and_then_stops_growing(connection, google):
    """Doubling without a cap means a connection broken for a week retries
    annually — which is indistinguishable from never."""
    assert sync.backoff_for(1) == sync.BACKOFF_BASE
    assert sync.backoff_for(2) == sync.BACKOFF_BASE * 2
    assert sync.backoff_for(3) == sync.BACKOFF_BASE * 4
    assert sync.backoff_for(500) == sync.BACKOFF_CAP


def test_a_recovered_sync_clears_the_notice(connection, google):
    """A notice that outlives the failure trains operators to ignore notices."""
    google["responses"] = [
        (503, {"error": {"message": "unavailable"}}),
        a_page([an_event("evt-1")]),
    ]
    sync.pull_connection(connection)

    sync.pull_connection(connection)

    connection.refresh_from_db()
    assert connection.sync_failures == 0
    assert connection.last_sync_error == ""
    assert connection.sync_backoff_until is None


def test_a_revoked_grant_marks_the_connection_rather_than_just_failing(
    connection, google
):
    """AC-4 of D-02 promised the operator a specific reconnect prompt. A sync
    that only counted the failure would leave the pane saying "connected"."""
    google["token_status"] = 400

    sync.pull_connection(connection)

    connection.refresh_from_db()
    assert connection.status == ConnectionStatus.NEEDS_RECONNECT


def test_one_unusable_event_does_not_lose_the_rest(connection, google):
    """`ends_at > starts_at` is a database constraint, so a malformed event
    would raise. Letting it abort the cycle loses every event after it."""
    good = an_event("evt-good")
    backwards = an_event("evt-bad")
    backwards["end"] = backwards["start"]
    google["responses"] = [a_page([backwards, good])]

    counts = sync.pull_connection(connection)

    assert counts["skipped"] == 1
    assert counts["created"] == 1
    assert ScheduledMeeting.objects.get().provider_event_id == "evt-good"


def test_one_tenants_failure_does_not_stop_the_sweep(connection, google):
    """A sweep that died on the first bad tenant would leave every connection
    it never reached looking healthy."""
    from apps.integrations.tasks import sync_calendars

    other = Tenant.objects.create(name="Other", schema_name="d03_other")
    second = CalendarConnection.objects.create(
        tenant=other, status=ConnectionStatus.CONNECTED
    )
    second.refresh_token = "refresh-def"
    second.save()
    google["responses"] = [
        (500, {"error": {"message": "boom"}}),
        a_page([an_event("evt-1")]),
    ]

    result = sync_calendars()

    assert result["failed"] == 1
    assert result["synced"] == 1


def test_the_sweep_respects_a_backoff(connection, google):
    from apps.integrations.tasks import sync_calendars

    connection.sync_backoff_until = timezone.now() + timedelta(hours=1)
    connection.save()

    result = sync_calendars()

    assert result == {"synced": 0, "failed": 0, "skipped": 1}
    assert not event_calls(google), "a backed-off connection must not be called"


def test_an_unconfigured_worker_does_not_sweep(connection, google, monkeypatch):
    """Same hazard as the token refresh: without credentials every call fails,
    and a sweep that recorded those failures would put the whole fleet into
    backoff over a missing env var."""
    from apps.integrations.tasks import sync_calendars

    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)

    sync_calendars()

    connection.refresh_from_db()
    assert connection.sync_failures == 0
    assert connection.sync_backoff_until is None


# ── §11 · external meetings are read-only here ───────────────────────


def external(connection, google, event_id="evt-1"):
    google["responses"] = [a_page([an_event(event_id)])]
    sync.pull_connection(connection)
    return ScheduledMeeting.objects.get(provider_event_id=event_id)


def test_an_external_meeting_reaches_the_pane_marked_unwritable(
    connection, google, api_client, editor
):
    """§11: external meetings appear "read-only alongside in-app ones so the
    operator has a single view". One endpoint, one window, one sorted list —
    with a flag saying which controls to disable."""
    external(connection, google)

    rows = api_client.get(EVENTS).json()
    rows = rows["results"] if isinstance(rows, dict) else rows

    assert len(rows) == 1
    assert rows[0]["origin"] == "GOOGLE"
    assert rows[0]["editable"] is False


def test_an_in_app_meeting_is_marked_writable(
    connection, tenant, session, api_client, editor
):
    """The control. A flag that read False for everything would pass the test
    above and disable the calendar."""
    ScheduledMeeting.objects.create(
        tenant=tenant,
        session=session,
        starts_at=timezone.now() + timedelta(days=1),
        ends_at=timezone.now() + timedelta(days=1, minutes=30),
        timezone="Europe/London",
    )

    rows = api_client.get(EVENTS).json()
    rows = rows["results"] if isinstance(rows, dict) else rows

    assert rows[0]["editable"] is True


@pytest.mark.parametrize("path", ["patch", "cancel"])
def test_editing_an_external_meeting_is_refused(
    connection, google, api_client, editor, path
):
    """Not merely cosmetic. If a client could edit one, the next pull would
    overwrite the edit — Google wins for externally created events — and the
    operator would watch their change evaporate with no explanation."""
    meeting = external(connection, google)

    if path == "patch":
        response = api_client.patch(
            f"{EVENTS}{meeting.pk}/", {"title": "Mine now"}, format="json"
        )
    else:
        response = api_client.post(f"{EVENTS}{meeting.pk}/cancel/", format="json")

    assert response.status_code == 403
    meeting.refresh_from_db()
    assert meeting.title == "Dentist"
    assert meeting.status == MeetingStatus.SCHEDULED


def test_a_client_cannot_declare_its_meeting_external(
    connection, session, api_client, editor
):
    """A meeting posted as GOOGLE would be uneditable the moment it existed,
    and the sync loop would believe Google owned it."""
    start = timezone.now() + timedelta(days=2)
    response = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=30)).isoformat(),
            "timezone": "Europe/London",
            "origin": "GOOGLE",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["origin"] == "APP"
    assert response.json()["editable"] is True


def test_an_in_app_meeting_still_requires_a_session(api_client, editor):
    """The regression the nullable column invites.

    `session` was made nullable so external events can share this table.
    ModelSerializer reads a nullable column as an optional field, which would
    let a client create an in-app meeting attached to nothing — a row D-01's
    cancel-releases-the-session rule has no meaning for.
    """
    start = timezone.now() + timedelta(days=2)
    response = api_client.post(
        EVENTS,
        {
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=30)).isoformat(),
            "timezone": "Europe/London",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "session" in response.json()


# ── AC-1 · "or immediately on manual refresh" ────────────────────────


def test_manual_refresh_pulls_now(connection, google, api_client, editor):
    google["responses"] = [a_page([an_event("evt-1")])]

    response = api_client.post(SYNC_NOW, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["result"]["created"] == 1
    assert ScheduledMeeting.objects.count() == 1


def test_manual_refresh_ignores_the_backoff(connection, google, api_client, editor):
    """The backoff exists to stop an automated sweep hammering a failing
    provider. A person pressing refresh is a different thing, and telling them
    to wait an hour is what AC-3 was written to prevent."""
    connection.sync_backoff_until = timezone.now() + timedelta(hours=1)
    connection.save()
    google["responses"] = [a_page([an_event("evt-1")])]

    api_client.post(SYNC_NOW, format="json")

    assert ScheduledMeeting.objects.count() == 1


def test_a_failed_manual_refresh_is_not_an_error_response(
    connection, google, api_client, editor
):
    """AC-3: the failure is "surfaced as a non-blocking notice". A 5xx here
    would make the pane's refresh button look broken rather than the sync."""
    google["responses"] = [(500, {"error": {"message": "boom"}})]

    response = api_client.post(SYNC_NOW, format="json")

    assert response.status_code == 200
    assert "error" in response.json()["result"]
    assert response.json()["connection"]["sync_failing"] is True


def test_manual_refresh_without_a_connection_is_a_404(api_client, editor, google):
    assert api_client.post(SYNC_NOW, format="json").status_code == 404


# ── Property · sync is idempotent, whatever arrives ──────────────────


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    ids=st.lists(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=3, max_size=8),
        min_size=1,
        max_size=6,
    ),
    repeats=st.integers(min_value=2, max_value=4),
)
def test_replaying_a_feed_never_multiplies_rows(connection, google, ids, repeats):
    """FR-CAL-03 generalised beyond the one case the requirement names.

    "No duplicate when sync runs twice" is a claim about *any* feed running
    *any* number of times, and the interesting inputs are the ones nobody
    writes by hand: the same event twice in one page, ids that differ only in
    case, a page replayed four times. The row count must equal the number of
    distinct ids, always.
    """
    ScheduledMeeting.objects.filter(tenant=connection.tenant).delete()
    connection.sync_token = ""
    connection.sync_backoff_until = None
    connection.sync_failures = 0
    connection.save()

    events = [an_event(event_id) for event_id in ids]
    google["responses"] = [
        a_page(events, sync_token=f"tok-{n}") for n in range(repeats)
    ]

    for _ in range(repeats):
        sync.pull_connection(connection)

    assert ScheduledMeeting.objects.filter(tenant=connection.tenant).count() == len(
        set(ids)
    )


def test_a_dead_cursor_is_discarded_even_if_the_retry_fails(connection, google):
    """The case that makes clearing the token on 410 load-bearing.

    When the retry succeeds the stale token is overwritten anyway, so nothing
    is proved. When it fails, a token left in place means every future cycle
    410s and sync is dead for good — silently, because a 410 is not an error
    anybody is paged about, and the connection still reads CONNECTED.
    """
    connection.sync_token = "stale-token"
    connection.save()
    google["responses"] = [
        (410, {"error": {"message": "Sync token is no longer valid"}}),
        (503, {"error": {"message": "unavailable"}}),
    ]

    sync.pull_connection(connection)

    connection.refresh_from_db()
    assert connection.sync_token == ""
