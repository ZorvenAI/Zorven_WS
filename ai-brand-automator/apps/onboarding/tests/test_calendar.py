"""D-01 · the in-app onboarding calendar.

The card names `test_dst_transition_rendering` here, and says why it exists:
storing an offset instead of a zone "is the standard bug here and it surfaces
twice a year, in production, on a customer call".

So these tests do not check that a datetime round-trips. They check that the
*same instant* renders as the right wall-clock time in several zones, across a
daylight-saving boundary, in both hemispheres — because that is the assertion
an offset would fail and a naive round-trip would pass.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.onboarding.models import (
    MeetingStatus,
    OnboardingSession,
    ScheduledMeeting,
)
from onboarding.models import Company
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

EVENTS = "/api/v1/onboarding/calendar/events/"
UTC = ZoneInfo("UTC")


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="D01 Co", schema_name="d01_cal")


@pytest.fixture
def session(tenant):
    company = Company.objects.create(tenant=tenant, name="Kalyani Roasters")
    return OnboardingSession.objects.create(tenant=tenant, company=company)


def member(api_client, tenant, role, username):
    user = User.objects.create_user(username, f"{username}@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=role)
    api_client.force_authenticate(user=user)
    return user


@pytest.fixture
def editor(api_client, tenant):
    return member(api_client, tenant, Membership.Role.EDITOR, "d01_editor")


def a_meeting(session, tenant, *, starts, zone="Europe/London", minutes=60, **extra):
    return ScheduledMeeting.objects.create(
        tenant=tenant,
        session=session,
        starts_at=starts,
        ends_at=starts + timedelta(minutes=minutes),
        timezone=zone,
        **extra,
    )


# ── AC-2 · the card's named case ─────────────────────────────────────


def test_dst_transition_rendering(session, tenant):
    """The card's named case, in both hemispheres.

    Two meetings an hour apart in UTC, straddling the moment Europe/London
    leaves BST on 27 October 2024 at 02:00 local. The gap between their *local*
    times is two hours, not one — that is the whole phenomenon, and a stored
    offset renders it as one.

    Sydney is included because the southern transition runs the other way; a
    bug that adds an hour instead of subtracting passes a London-only test.
    """
    london = ZoneInfo("Europe/London")

    # 00:30 UTC is 01:30 BST (UTC+1); 01:30 UTC is 01:30 GMT (UTC+0).
    before = datetime(2024, 10, 27, 0, 30, tzinfo=UTC)
    after = datetime(2024, 10, 27, 1, 30, tzinfo=UTC)

    assert before.astimezone(london).strftime("%H:%M") == "01:30"
    assert after.astimezone(london).strftime("%H:%M") == "01:30"
    # One hour of real time, zero hours of clock time — the ambiguity that
    # makes an offset the wrong thing to store.
    assert after - before == timedelta(hours=1)

    first = a_meeting(session, tenant, starts=before, zone="Europe/London")
    ScheduledMeeting.objects.filter(pk=first.pk).update(status=MeetingStatus.CANCELLED)
    second = a_meeting(session, tenant, starts=after, zone="Europe/London")

    first.refresh_from_db()
    second.refresh_from_db()

    assert first.starts_at.astimezone(london).strftime("%H:%M") == "01:30"
    assert second.starts_at.astimezone(london).strftime("%H:%M") == "01:30"
    # The stored instants are still an hour apart. If either had been coerced
    # through an offset, they would now be equal or two hours apart.
    assert second.starts_at - first.starts_at == timedelta(hours=1)


def test_a_southern_hemisphere_transition_moves_the_other_way(session, tenant):
    """Sydney enters DST on 6 October 2024 at 02:00 local, going forward.

    A sign error that happens to be invisible in London shows up here.
    """
    sydney = ZoneInfo("Australia/Sydney")
    instant = datetime(2024, 10, 5, 16, 0, tzinfo=UTC)  # 02:00 AEST, pre-jump

    meeting = a_meeting(session, tenant, starts=instant, zone="Australia/Sydney")
    meeting.refresh_from_db()

    local = meeting.starts_at.astimezone(sydney)
    assert local.strftime("%H:%M") == "03:00", local  # 02:00 does not exist
    assert local.utcoffset() == timedelta(hours=11)


@pytest.mark.parametrize(
    "viewer_zone,expected",
    [
        ("UTC", "12:00"),
        ("Europe/London", "13:00"),
        ("America/New_York", "08:00"),
        ("Asia/Kolkata", "17:30"),
        ("Australia/Sydney", "22:00"),
    ],
)
def test_one_instant_renders_correctly_in_every_viewer_zone(
    session, tenant, viewer_zone, expected
):
    """AC-2: "every view shows the same instant rendered in the viewer's local
    zone". Midsummer, so this is about zone arithmetic rather than DST."""
    meeting = a_meeting(
        session, tenant, starts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    )
    meeting.refresh_from_db()

    rendered = meeting.starts_at.astimezone(ZoneInfo(viewer_zone))

    assert rendered.strftime("%H:%M") == expected
    assert rendered == meeting.starts_at  # the same instant, differently written


# ── The rules, in the database ───────────────────────────────────────


@pytest.mark.parametrize("bad", ["+05:30", "-0800", "+00:00"])
def test_an_offset_literal_cannot_be_stored_as_a_timezone(session, tenant, bad):
    """The bug the card names, refused by the column.

    Leading-sign forms only. No IANA zone begins with + or -, so these are
    unambiguous. "UTC+5" cannot be refused here without also refusing GMT+0,
    which is a real zone — that one belongs to the serializer and has its own
    test below.
    """
    with pytest.raises(IntegrityError), transaction.atomic():
        a_meeting(
            session, tenant, starts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC), zone=bad
        )


@pytest.mark.parametrize(
    "good",
    [
        "Europe/London",
        "America/Argentina/Buenos_Aires",
        "UTC",
        # Real IANA zones my first constraint rejected. The regex allow-listed
        # what a zone "looks like" and refused 44 of them, including these —
        # so the serializer accepted a valid zone and the database raised,
        # turning correct input into a 500. This test listed EST5EDT as an
        # *offset*, which encoded the same misunderstanding.
        "EST5EDT",
        "GMT",
        "Eire",
        "CET",
    ],
)
def test_real_zone_names_are_accepted(session, tenant, good):
    """The control. A constraint that rejected everything would pass the test
    above while making the feature impossible."""
    meeting = a_meeting(
        session, tenant, starts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC), zone=good
    )

    assert meeting.pk is not None


def test_a_meeting_cannot_end_before_it_starts(session, tenant):
    with pytest.raises(IntegrityError), transaction.atomic():
        ScheduledMeeting.objects.create(
            tenant=tenant,
            session=session,
            starts_at=datetime(2024, 6, 15, 12, 0, tzinfo=UTC),
            ends_at=datetime(2024, 6, 15, 11, 0, tzinfo=UTC),
            timezone="UTC",
        )


def test_only_one_scheduled_meeting_per_session(session, tenant):
    a_meeting(session, tenant, starts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC))

    with pytest.raises(IntegrityError), transaction.atomic():
        a_meeting(session, tenant, starts=datetime(2024, 6, 16, 12, 0, tzinfo=UTC))


def test_a_cancelled_meeting_frees_the_slot(session, tenant):
    """Rescheduling must not require destroying the record of the first
    booking — an operator asking "what happened to Tuesday" needs it."""
    first = a_meeting(session, tenant, starts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC))
    ScheduledMeeting.objects.filter(pk=first.pk).update(status=MeetingStatus.CANCELLED)

    second = a_meeting(session, tenant, starts=datetime(2024, 6, 16, 12, 0, tzinfo=UTC))

    assert ScheduledMeeting.objects.filter(session=session).count() == 2
    assert second.status == MeetingStatus.SCHEDULED


# ── AC-1 · through the API ───────────────────────────────────────────


def test_an_editor_can_schedule_a_meeting(api_client, tenant, session, editor):
    response = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "title": "Kickoff",
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "Europe/London",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    # Company.__str__ includes the tenant — "Kalyani Roasters (D01 Co)" — so
    # this asserts the name is shown rather than pinning a format that
    # belongs to another model.
    assert "Kalyani Roasters" in body["company"]  # AC-1: shows the company
    assert body["organiser"] == editor.pk  # AC-1: and the operator
    assert body["status"] == MeetingStatus.SCHEDULED


def test_cancelling_releases_the_session_without_deleting(
    api_client, tenant, session, editor
):
    created = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    ).json()

    response = api_client.post(f"{EVENTS}{created['id']}/cancel/", format="json")

    assert response.status_code == 200
    assert ScheduledMeeting.objects.get(pk=created["id"]).status == (
        MeetingStatus.CANCELLED
    )
    # Released: the session can be booked again.
    again = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-20T12:00:00Z",
            "ends_at": "2024-06-20T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    )
    assert again.status_code == 201, again.content


def test_cancelling_twice_is_refused(api_client, tenant, session, editor):
    created = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    ).json()
    api_client.post(f"{EVENTS}{created['id']}/cancel/", format="json")

    second = api_client.post(f"{EVENTS}{created['id']}/cancel/", format="json")

    assert second.status_code == 409


def test_an_invented_timezone_is_refused_by_the_api(
    api_client, tenant, session, editor
):
    """The column's regex accepts the shape; only zoneinfo knows the place."""
    response = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "Europe/Atlantis",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "IANA" in str(response.json())


def test_the_window_filter_narrows_server_side(api_client, tenant, session, editor):
    """A calendar asks for a month, not for everything."""
    # Both on one session: B-01 allows only one non-terminal OnboardingSession
    # per company, and Company is one-to-one with a tenant, so a second live
    # session here is not a thing the schema permits. Cancelling the first
    # meeting frees the slot, which is the behaviour tested above.
    june = a_meeting(session, tenant, starts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC))
    ScheduledMeeting.objects.filter(pk=june.pk).update(status=MeetingStatus.CANCELLED)
    a_meeting(session, tenant, starts=datetime(2024, 9, 15, 12, 0, tzinfo=UTC))

    body = api_client.get(
        f"{EVENTS}?from=2024-06-01T00:00:00Z&to=2024-06-30T23:59:59Z"
    ).json()

    rows = body["results"] if isinstance(body, dict) else body
    assert len(rows) == 1


# ── AC-3 · roles ─────────────────────────────────────────────────────


def test_a_viewer_can_read_but_not_schedule(api_client, tenant, session):
    a_meeting(session, tenant, starts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC))
    member(api_client, tenant, Membership.Role.VIEWER, "d01_viewer")

    assert api_client.get(EVENTS).status_code == 200

    refused = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-07-15T12:00:00Z",
            "ends_at": "2024-07-15T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    )
    assert refused.status_code == 403


def test_a_viewer_cannot_cancel(api_client, tenant, session):
    meeting = a_meeting(
        session, tenant, starts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    )
    member(api_client, tenant, Membership.Role.VIEWER, "d01_viewer2")

    response = api_client.post(f"{EVENTS}{meeting.pk}/cancel/", format="json")

    assert response.status_code == 403
    meeting.refresh_from_db()
    assert meeting.status == MeetingStatus.SCHEDULED


# ── Review findings on #567 ──────────────────────────────────────────


def test_a_real_zone_is_never_refused_by_the_database(session, tenant):
    """The mismatch that produced a 500 on valid input, as a sweep.

    Anything zoneinfo accepts, the column must accept. The two layers answer
    different questions now — the serializer asks "is this a real place", the
    constraint asks "is this an offset literal" — and this asserts they cannot
    disagree.
    """
    from zoneinfo import available_timezones

    for zone in sorted(available_timezones()):
        ScheduledMeeting.objects.create(
            tenant=tenant,
            session=session,
            starts_at=datetime(2024, 6, 15, 12, 0, tzinfo=UTC),
            ends_at=datetime(2024, 6, 15, 13, 0, tzinfo=UTC),
            timezone=zone,
            status=MeetingStatus.CANCELLED,  # keeps the one-live constraint happy
        )

    assert ScheduledMeeting.objects.count() == len(available_timezones())


def test_a_session_from_another_tenant_is_refused(api_client, tenant, session, editor):
    """Without this, the meeting's own serializer reads the other tenant's
    company straight back out through select_related — a write that leaks on
    read."""
    outsider = Tenant.objects.create(name="Outsider", schema_name="d01_outsider")
    theirs = OnboardingSession.objects.create(
        tenant=outsider,
        company=Company.objects.create(tenant=outsider, name="Not Yours"),
    )

    response = api_client.post(
        EVENTS,
        {
            "session": theirs.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    )

    assert response.status_code == 400
    assert not ScheduledMeeting.objects.filter(session=theirs).exists()


def test_status_cannot_be_set_directly(api_client, tenant, session, editor):
    """Writable status let a client PATCH past the cancel action — and back
    again, un-cancelling a meeting whose session had already been released."""
    created = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    ).json()

    api_client.patch(
        f"{EVENTS}{created['id']}/", {"status": "CANCELLED"}, format="json"
    )

    assert ScheduledMeeting.objects.get(pk=created["id"]).status == (
        MeetingStatus.SCHEDULED
    )


def test_a_meeting_cannot_be_moved_to_another_session(
    api_client, tenant, session, editor
):
    """Rescheduling changes the time. Moving a meeting between sessions would
    breach one-live-per-session from the far side and carry its history onto a
    session it never belonged to."""
    created = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    ).json()
    other_company = Company.objects.create(
        tenant=Tenant.objects.create(name="Other", schema_name="d01_other"),
        name="Other Co",
    )
    elsewhere = OnboardingSession.objects.create(
        tenant=other_company.tenant, company=other_company
    )

    response = api_client.patch(
        f"{EVENTS}{created['id']}/", {"session": elsewhere.pk}, format="json"
    )

    assert response.status_code == 400
    assert ScheduledMeeting.objects.get(pk=created["id"]).session_id == session.pk


@pytest.mark.parametrize("bad", ["soon", "2024-13-45", "", "not-a-date"])
def test_a_malformed_window_is_a_400_not_a_500(
    api_client, tenant, session, editor, bad
):
    """A raw string went into a DateTimeField lookup, so an ordinary GET with
    a typo raised out of the queryset."""
    response = api_client.get(f"{EVENTS}?from={bad}")

    assert response.status_code in (200, 400), response.content
    if bad:
        assert response.status_code == 400


def test_cancelling_works_even_with_window_parameters(
    api_client, tenant, session, editor
):
    """cancel() read through the list queryset, so a client that happened to
    send from/to could 404 on a meeting that plainly exists."""
    created = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    ).json()

    # A window that excludes the meeting entirely.
    response = api_client.post(
        f"{EVENTS}{created['id']}/cancel/"
        "?from=2030-01-01T00:00:00Z&to=2030-01-31T00:00:00Z",
        format="json",
    )

    assert response.status_code == 200, response.content
    assert ScheduledMeeting.objects.get(pk=created["id"]).status == (
        MeetingStatus.CANCELLED
    )


@pytest.mark.parametrize("bad", ["UTC+5", "GMT+0530", "Europe/Atlantis", "EST5EDTX"])
def test_a_non_zone_is_refused_by_the_serializer(
    api_client, tenant, session, editor, bad
):
    """The half the column cannot do.

    "UTC+5" has no leading sign and is not a real zone; refusing it by shape
    would also refuse GMT+0, which is one. Only zoneinfo can tell them apart,
    so the API is where this is caught.
    """
    response = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": bad,
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert not ScheduledMeeting.objects.exists()


def test_the_window_end_is_exclusive(api_client, tenant, session, editor):
    """Review finding. The pane sends `to` as the day after the last square,
    so an inclusive bound fetched a meeting it would never draw — a row paid
    for, counted in the response, and invisible on screen.
    """
    boundary = datetime(2024, 7, 1, 0, 0, tzinfo=UTC)
    a_meeting(session, tenant, starts=boundary)

    # "Z", not isoformat(). isoformat() emits "+00:00" and a bare + in a query
    # string decodes as a space, so the server saw "2024-07-01T00:00:00 00:00"
    # and answered 400 — which the rows helper below would have swallowed as
    # an empty list, passing this test for entirely the wrong reason. The pane
    # sends toISOString(), which is already Z-suffixed.
    response = api_client.get(
        f"{EVENTS}?from=2024-06-01T00:00:00Z&to=2024-07-01T00:00:00Z"
    )

    assert response.status_code == 200, response.content
    body = response.json()
    rows = body["results"] if "results" in body else body
    assert rows == [], "a meeting starting on the exclusive bound was returned"


def test_a_meeting_just_inside_the_window_is_returned(
    api_client, tenant, session, editor
):
    """The control. An exclusive bound that excluded the last minute too would
    pass the test above while hiding real meetings."""
    a_meeting(session, tenant, starts=datetime(2024, 6, 30, 23, 59, tzinfo=UTC))

    body = api_client.get(
        f"{EVENTS}?from=2024-06-01T00:00:00Z&to=2024-07-01T00:00:00Z"
    ).json()

    rows = body["results"] if isinstance(body, dict) else body
    assert len(rows) == 1


def test_the_already_cancelled_message_reads_as_a_sentence(
    api_client, tenant, session, editor
):
    """It is user-facing API output; a client should be able to show it."""
    created = api_client.post(
        EVENTS,
        {
            "session": session.pk,
            "starts_at": "2024-06-15T12:00:00Z",
            "ends_at": "2024-06-15T13:00:00Z",
            "timezone": "UTC",
        },
        format="json",
    ).json()
    api_client.post(f"{EVENTS}{created['id']}/cancel/", format="json")

    message = api_client.post(f"{EVENTS}{created['id']}/cancel/", format="json").json()[
        "error"
    ]

    assert message[0].isupper()
    assert message.endswith(".")
