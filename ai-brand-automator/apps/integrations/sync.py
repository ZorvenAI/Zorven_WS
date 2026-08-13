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
from apps.onboarding.models import MeetingOrigin, MeetingStatus, ScheduledMeeting

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

    counts = {"created": 0, "updated": 0, "cancelled": 0, "skipped": 0}
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

    if owned_meeting_id(event, connection.tenant_id) is not None:
        # Ours. The inbound half does not touch app-owned events at all — AC-4
        # gives in-app the win, and the outbound half is what enforces it.
        counts["skipped"] += 1
        return

    if event.get("status") == "cancelled":
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
