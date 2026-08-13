"""Pulling Google Calendar into the in-app calendar (D-03, AC-1).

The outbound half — pushing app-created meetings to Google — lands in the
next PR. This module deliberately reads only.

Ownership vocabulary, because AC-4 turns on it: an event this app created
carries a private extended property naming the meeting it came from, so
"onboarding-owned" is a fact read off the event rather than a guess made from
its title. Everything without that tag is somebody else's diary entry, which
this app mirrors read-only and never edits.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from decouple import config
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.integrations import calendar_api, google_calendar
from apps.integrations.models import CalendarConnection, ConnectionStatus
from apps.onboarding.models import (
    CalendarSyncConflict,
    ConflictWinner,
    MeetingOrigin,
    MeetingStatus,
    ScheduledMeeting,
)

logger = logging.getLogger(__name__)

#: The private extended property that marks an event as ours.
TAG_KEY = "zorven_meeting_ref"

#: How far back a first sync reads. A new connection with no cursor has to
#: choose a horizon; a year of history on a calendar the operator has used for
#: a decade is a large first read for very little value, and the onboarding
#: calendar is a forward-looking artefact.
FIRST_SYNC_LOOKBACK = timedelta(days=30)

#: AC-3's backoff. Doubles per consecutive failure, capped so a connection
#: that has been broken for a week still retries hourly rather than annually.
BACKOFF_BASE = timedelta(minutes=5)
BACKOFF_CAP = timedelta(hours=1)


def namespace() -> str:
    """Distinguishes this deployment's tags from another's.

    Google's "private" extended properties are private to the *calendar*, not
    to the application: a staging deployment and production, both syncing the
    same operator's calendar, read each other's tags. With integer meeting IDs
    they would also collide outright, and staging would claim ownership of a
    production meeting.
    """
    return config("CALENDAR_SYNC_NAMESPACE", default="zorven").strip() or "zorven"


def tag_for(meeting: ScheduledMeeting) -> str:
    return f"{namespace()}:{meeting.tenant_id}:{meeting.pk}"


def owned_meeting_id(event: dict, tenant_id: int | None) -> int | None:
    """The meeting an event came from, or None if it is not this tenant's.

    All three parts of the tag are checked, which is the point of carrying
    three. The tenant part matters as much as the deployment one: two tenants
    can connect the same Google account — a consultancy onboarding several
    brands from one calendar is the ordinary case — and a tag naming tenant A,
    read during tenant B's sync, is not B's meeting. It is an external event
    as far as B is concerned, and treating it as owned means B never sees a
    meeting that is on their own calendar.
    """
    private = ((event.get("extendedProperties") or {}).get("private")) or {}
    raw = private.get(TAG_KEY)
    if not isinstance(raw, str):
        return None
    parts = raw.split(":")
    if len(parts) != 3 or parts[0] != namespace():
        return None
    if parts[1] != str(tenant_id):
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


def backoff_for(failures: int) -> timedelta:
    """Exponential, capped. `failures` is the count *including* this one."""
    if failures < 1:
        return BACKOFF_BASE
    # Shift rather than pow, and clamp the exponent: a connection left broken
    # for months would otherwise compute a timedelta big enough to overflow.
    return min(BACKOFF_CAP, BACKOFF_BASE * (2 ** min(failures - 1, 16)))


def due(connection: CalendarConnection, *, now=None) -> bool:
    now = now or timezone.now()
    return not (connection.sync_backoff_until and connection.sync_backoff_until > now)


def pull_connection(connection: CalendarConnection) -> dict:
    """Read one tenant's calendar into the in-app one.

    Never raises. AC-3: "the in-app calendar continues to function fully" —
    which means a tenant whose Google is on fire must not take down the sweep,
    and must not take down their own calendar either. Failures are recorded on
    the connection and surfaced through the status endpoint.
    """
    token = connection.refresh_token
    if not token:
        return _record_failure(connection, "No refresh token; reconnect required.")

    try:
        tokens = google_calendar.refresh(refresh_token=token)
    except google_calendar.OAuthError as exc:
        # The grant is gone rather than the API being unhappy. Marking it is
        # what AC-4 of D-02 promised the operator.
        connection.status = ConnectionStatus.NEEDS_RECONNECT
        connection.last_error = exc.reason[:255]
        connection.save(update_fields=["status", "last_error", "updated_at"])
        return _record_failure(connection, exc.reason)

    access_token = tokens.get("access_token") or ""
    if not access_token:
        return _record_failure(connection, "Google returned no access token.")

    try:
        page = _read(connection, access_token)
    except calendar_api.CalendarApiError as exc:
        return _record_failure(connection, exc.reason)

    counts = {"created": 0, "updated": 0, "cancelled": 0, "skipped": 0, "conflicts": 0}
    for event in page.events:
        try:
            _apply(connection, event, counts)
        except IntegrityError:
            # A concurrent cycle won the race for this event. The constraint
            # did its job; there is nothing to repair and nothing to report.
            counts["skipped"] += 1
            logger.info(
                "calendar_sync_event_raced",
                extra={"tenant_id": connection.tenant_id},
            )

    # Push after pulling, on the same access token. In that order because a
    # conflict detected on the way in nulls provider_synced_at, and the push
    # in this very cycle is what reasserts the in-app copy — waiting three
    # minutes would leave the two sides disagreeing in between.
    counts.update(push_connection(connection, access_token))

    connection.sync_token = page.next_sync_token or connection.sync_token
    connection.last_sync_at = timezone.now()
    connection.last_sync_error = ""
    connection.sync_failures = 0
    connection.sync_backoff_until = None
    connection.save(
        update_fields=[
            "sync_token",
            "last_sync_at",
            "last_sync_error",
            "sync_failures",
            "sync_backoff_until",
            "updated_at",
        ]
    )
    return counts


def _read(connection: CalendarConnection, access_token: str):
    """One incremental read, falling back to a full one when the cursor dies."""
    try:
        return calendar_api.list_events(
            access_token=access_token,
            sync_token=connection.sync_token,
            time_min=timezone.now() - FIRST_SYNC_LOOKBACK,
        )
    except calendar_api.SyncTokenExpired:
        # Google expires tokens on its own schedule. Keeping the dead one would
        # mean every future cycle 410s and sync stops for good — silently,
        # because a 410 is not an error anybody is paged about.
        logger.info(
            "calendar_sync_token_expired",
            extra={"tenant_id": connection.tenant_id},
        )
        connection.sync_token = ""
        connection.save(update_fields=["sync_token", "updated_at"])
        return calendar_api.list_events(
            access_token=access_token,
            sync_token="",
            time_min=timezone.now() - FIRST_SYNC_LOOKBACK,
        )


def _apply(connection: CalendarConnection, event: dict, counts: dict) -> None:
    """Reconcile one Google event into the in-app calendar."""
    event_id = str(event.get("id") or "")
    if not event_id:
        counts["skipped"] += 1
        return

    if event.get("status") == "cancelled":
        # Handled *before* the tag check, and matched on the provider event id
        # rather than on ownership, because a Google deletion marker is only
        # `{id, status: cancelled}` — it carries no extendedProperties. Read
        # tag-first, a deleted app-owned event looks like a stranger's, and
        # AC-4's "in-app wins" would never fire for the one case operators
        # actually hit: somebody clearing their calendar.
        owned = ScheduledMeeting.objects.filter(
            tenant=connection.tenant,
            provider_event_id=event_id,
            origin=MeetingOrigin.APP,
        ).first()
        if owned is not None:
            _resurrect(owned, event_id, counts)
            return

        # Only reachable on an incremental read; a full read never returns
        # them. Cancel our mirror rather than deleting it, matching D-01's
        # rule that a cancelled meeting keeps its row.
        updated = (
            ScheduledMeeting.objects.filter(
                tenant=connection.tenant,
                provider_event_id=event_id,
                origin=MeetingOrigin.GOOGLE,
            )
            .exclude(status=MeetingStatus.CANCELLED)
            .update(status=MeetingStatus.CANCELLED, updated_at=timezone.now())
        )
        counts["cancelled"] += updated
        if not updated:
            counts["skipped"] += 1
        return

    meeting_id = owned_meeting_id(event, connection.tenant_id)
    if meeting_id is not None:
        # Ours, come back. Not skipped: AC-4 says the losing change is
        # "recorded rather than discarded silently", and skipping is precisely
        # discarding it silently.
        reconcile_owned(connection, event, meeting_id, counts)
        return

    starts_at, zone = calendar_api.event_instant(event.get("start"))
    ends_at, end_zone = calendar_api.event_instant(event.get("end"))
    if starts_at is None or ends_at is None or ends_at <= starts_at:
        # `ends_at > starts_at` is a database constraint, so writing this row
        # would raise. Skipping loses one malformed event; letting it through
        # would abort the cycle and lose every event after it.
        counts["skipped"] += 1
        logger.info(
            "calendar_sync_event_unusable",
            extra={"tenant_id": connection.tenant_id, "provider_event_id": event_id},
        )
        return

    defaults = {
        "starts_at": starts_at,
        "ends_at": ends_at,
        # Never an offset: D-01's column refuses one, and UTC is the honest
        # answer when Google does not say.
        "timezone": zone or end_zone or "UTC",
        "title": str(event.get("summary") or "")[:255],
        "status": MeetingStatus.SCHEDULED,
        "origin": MeetingOrigin.GOOGLE,
        "provider_updated_at": parse_datetime(event.get("updated") or ""),
        "session": None,
    }

    with transaction.atomic():
        existing = (
            ScheduledMeeting.objects.select_for_update()
            .filter(tenant=connection.tenant, provider_event_id=event_id)
            .first()
        )
        if existing is not None and existing.origin == MeetingOrigin.APP:
            # An app-created meeting whose tag has been stripped — an operator
            # can edit extended properties away, and some calendar clients do
            # it for them. Rewriting it to GOOGLE would hand ownership to the
            # other side and quietly invert AC-4 for that meeting, so the
            # inbound half leaves it alone and lets the outbound half reassert
            # the tag.
            counts["skipped"] += 1
            logger.info(
                "calendar_sync_untagged_app_event",
                extra={
                    "tenant_id": connection.tenant_id,
                    "provider_event_id": event_id,
                },
            )
            return

        if existing is None:
            ScheduledMeeting.objects.create(
                tenant=connection.tenant, provider_event_id=event_id, **defaults
            )
            counts["created"] += 1
        else:
            for attribute, value in defaults.items():
                setattr(existing, attribute, value)
            existing.save()
            counts["updated"] += 1


def _record_failure(connection: CalendarConnection, reason: str) -> dict:
    """AC-3: non-fatal, visible, and retried with backoff."""
    connection.sync_failures += 1
    connection.last_sync_error = reason[:255]
    connection.sync_backoff_until = timezone.now() + backoff_for(
        connection.sync_failures
    )
    connection.save(
        update_fields=[
            "sync_failures",
            "last_sync_error",
            "sync_backoff_until",
            "updated_at",
        ]
    )
    logger.warning(
        "calendar_sync_failed",
        extra={
            "tenant_id": connection.tenant_id,
            "secret_path": connection.secret_path,
            "reason": reason,
            "consecutive_failures": connection.sync_failures,
        },
    )
    return {"error": reason, "failures": connection.sync_failures}


# ── Outbound (AC-2) and reconciliation (AC-4) ────────────────────────


def event_body(meeting: ScheduledMeeting) -> dict:
    """The Google event for an in-app meeting.

    Attendees are the one part of AC-2 the data model cannot fully answer:
    nothing in this system records who a meeting is *with*. D-01 modelled no
    invitees, Company carries no contact address, and no story adds either. So
    the organiser — the only participant with a known email — is what goes
    out. Raised as a gap rather than papered over with an invented field.
    """
    attendees = []
    email = getattr(meeting.organiser, "email", "") or ""
    if email:
        attendees.append({"email": email})

    return {
        "summary": meeting.title or "Onboarding meeting",
        "start": {
            "dateTime": meeting.starts_at.isoformat().replace("+00:00", "Z"),
            "timeZone": meeting.timezone,
        },
        "end": {
            "dateTime": meeting.ends_at.isoformat().replace("+00:00", "Z"),
            "timeZone": meeting.timezone,
        },
        "attendees": attendees,
        # What makes AC-4 decidable on the way back in.
        "extendedProperties": {"private": {TAG_KEY: tag_for(meeting)}},
    }


def _remote_shape(event: dict) -> dict:
    """The parts of a Google event this app claims authority over.

    Comparison is by value, not by timestamp. Google's `updated` moves when
    *we* write too, so a timestamp check would report a conflict every time we
    pushed — and the recorded "losing change" would be our own.
    """
    starts_at, _ = calendar_api.event_instant(event.get("start"))
    ends_at, _ = calendar_api.event_instant(event.get("end"))
    return {
        "summary": str(event.get("summary") or ""),
        "starts_at": starts_at.isoformat() if starts_at else None,
        "ends_at": ends_at.isoformat() if ends_at else None,
    }


def _local_shape(meeting: ScheduledMeeting) -> dict:
    return {
        "summary": meeting.title or "Onboarding meeting",
        "starts_at": meeting.starts_at.isoformat(),
        "ends_at": meeting.ends_at.isoformat(),
    }


def needs_push(meeting: ScheduledMeeting) -> bool:
    """Whether anything has changed since the last push.

    `provider_synced_at` is written with ``QuerySet.update()`` so that pushing
    does not bump ``updated_at``. Were it saved normally, every meeting would
    look permanently dirty and the sweep would patch the whole calendar every
    three minutes — the quota burn the card warns about, arriving by the other
    door.
    """
    if meeting.provider_synced_at is None:
        return True
    return meeting.updated_at > meeting.provider_synced_at


def record_conflict(meeting, *, winner, discarded, rule) -> None:
    """AC-4: "the losing change is recorded rather than discarded silently"."""
    CalendarSyncConflict.objects.create(
        tenant=meeting.tenant,
        meeting=meeting,
        winner=winner,
        discarded=discarded,
        rule=rule,
    )
    logger.info(
        "calendar_sync_conflict",
        extra={
            "tenant_id": meeting.tenant_id,
            "meeting_id": meeting.pk,
            "winner": winner,
        },
    )


def _resurrect(meeting: ScheduledMeeting, event_id: str, counts: dict) -> None:
    """An onboarding meeting deleted in Google. AC-4: in-app wins.

    So it comes back. Clearing the provider id is what makes the push
    re-create it — the old event cannot be patched back into existence — and
    the deletion is recorded rather than quietly undone, because somebody
    meant it and will want to know why it did not stick.
    """
    if meeting.status == MeetingStatus.CANCELLED:
        counts["skipped"] += 1
        return

    record_conflict(
        meeting,
        winner=ConflictWinner.APP,
        discarded={"status": "cancelled", "provider_event_id": event_id},
        rule="in-app wins for onboarding-owned events",
    )
    ScheduledMeeting.objects.filter(pk=meeting.pk).update(
        provider_event_id="", provider_synced_at=None
    )
    counts["conflicts"] += 1


def reconcile_owned(connection, event: dict, meeting_id: int, counts: dict) -> None:
    """An event we created, come back changed. AC-4's first half.

    The rule: in-app wins for onboarding-owned events. So a remote edit is
    recorded and then overwritten — not silently, and not by leaving the two
    sides disagreeing until somebody notices.
    """
    meeting = ScheduledMeeting.objects.filter(
        pk=meeting_id, tenant=connection.tenant, origin=MeetingOrigin.APP
    ).first()
    if meeting is None:
        # A tag naming a meeting this tenant does not have. Another
        # deployment's row id under our namespace, or one we deleted. Not ours
        # to act on either way.
        counts["skipped"] += 1
        return

    if event.get("status") == "cancelled":
        _resurrect(meeting, str(event.get("id") or ""), counts)
        return

    if meeting.provider_event_id != str(event.get("id") or ""):
        # The tag is authoritative about which meeting an event belongs to, so
        # a row that has lost its id adopts this one back.
        #
        # It gets lost by an ordinary sequence: something loads a meeting, the
        # sweep pushes it and writes the id, and the holder then calls save()
        # — a full-field write from a stale instance, which is what
        # ModelSerializer.update() does. Without this, the next push sees no
        # id, inserts, and the operator has two copies of the same meeting in
        # their calendar. That is precisely the duplicate FR-CAL-03 forbids,
        # arriving by a race rather than by a second cycle.
        ScheduledMeeting.objects.filter(pk=meeting.pk).update(
            provider_event_id=str(event.get("id") or "")
        )
        meeting.refresh_from_db(fields=["provider_event_id"])
        logger.info(
            "calendar_sync_readopted_event",
            extra={"tenant_id": meeting.tenant_id, "meeting_id": meeting.pk},
        )

    remote, local = _remote_shape(event), _local_shape(meeting)
    if remote == local:
        counts["skipped"] += 1
        return

    record_conflict(
        meeting,
        winner=ConflictWinner.APP,
        discarded=remote,
        rule="in-app wins for onboarding-owned events",
    )
    # Null the marker rather than push from here: the push half owns talking
    # to Google, and doing it in both places is how two writers appear.
    ScheduledMeeting.objects.filter(pk=meeting.pk).update(provider_synced_at=None)
    counts["conflicts"] += 1


def push_connection(connection: CalendarConnection, access_token: str) -> dict:
    """Send in-app meetings outward (AC-2).

    Insert what has never been pushed, patch what has changed, delete what has
    been cancelled. Nothing else — a meeting that has not moved costs no call,
    which is what keeps a three-minute cadence affordable.
    """
    counts = {"inserted": 0, "patched": 0, "deleted": 0, "failed": 0}

    candidates = ScheduledMeeting.objects.filter(
        tenant=connection.tenant, origin=MeetingOrigin.APP
    ).select_related("organiser")

    for meeting in candidates:
        if not needs_push(meeting):
            continue
        try:
            _push_one(meeting, access_token, counts)
        except calendar_api.CalendarApiError as exc:
            # One meeting's failure must not abandon the rest. It stays dirty
            # and is retried next cycle.
            counts["failed"] += 1
            logger.warning(
                "calendar_push_failed",
                extra={
                    "tenant_id": connection.tenant_id,
                    "meeting_id": meeting.pk,
                    "reason": exc.reason,
                },
            )
    return counts


def _push_one(meeting: ScheduledMeeting, access_token: str, counts: dict) -> None:
    now = timezone.now()

    if meeting.status == MeetingStatus.CANCELLED:
        if not meeting.provider_event_id:
            # Cancelled before it was ever pushed. Marking it synced stops the
            # sweep reconsidering it forever.
            ScheduledMeeting.objects.filter(pk=meeting.pk).update(
                provider_synced_at=now
            )
            return
        calendar_api.delete_event(
            access_token=access_token, event_id=meeting.provider_event_id
        )
        ScheduledMeeting.objects.filter(pk=meeting.pk).update(provider_synced_at=now)
        counts["deleted"] += 1
        return

    body = event_body(meeting)

    if meeting.provider_event_id:
        calendar_api.patch_event(
            access_token=access_token,
            event_id=meeting.provider_event_id,
            body=body,
        )
        ScheduledMeeting.objects.filter(pk=meeting.pk).update(provider_synced_at=now)
        counts["patched"] += 1
        return

    created = calendar_api.insert_event(access_token=access_token, body=body)
    event_id = str(created.get("id") or "")
    if not event_id:
        raise calendar_api.CalendarApiError("Google created an event with no id")

    # update(), not save(): save() would bump `updated_at` and the meeting
    # would look dirty again on the very next cycle, patching itself forever.
    ScheduledMeeting.objects.filter(pk=meeting.pk).update(
        provider_event_id=event_id, provider_synced_at=now
    )
    counts["inserted"] += 1
