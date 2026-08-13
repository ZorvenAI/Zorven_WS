"""The Google Calendar REST API, as much of it as D-03 needs.

Raw ``requests``, matching ``google_calendar.py``. Adding
``google-api-python-client`` would pull a large dependency tree in to save a
handful of URL constructions, and — the deciding reason — its transport is
hard to point at a local server, which is what lets the tests here drive *this*
code rather than a mock of it.

Endpoint URLs come from :func:`_base` for the same reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from decouple import config
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.integrations.google_calendar import OAuthError

logger = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/calendar/v3"

#: Which calendar. `primary` is the operator's own, which is what a Google
#: Calendar connection means to the person who clicked connect.
CALENDAR_ID = "primary"

TIMEOUT_S = 20

#: Google's own ceiling is 2500. A smaller page means more round trips on the
#: first sync and a shorter transaction on every later one; incremental syncs
#: almost always fit in a single page anyway.
PAGE_SIZE = 250

#: A page loop that cannot end is a worker that never returns. Google paginates
#: an incremental sync in single figures; a thousand pages is not a large
#: calendar, it is a bug at one end or the other.
MAX_PAGES = 1000


class CalendarApiError(OAuthError):
    """A call to the Calendar API failed.

    Subclasses OAuthError so a caller that already handles the connection
    going bad does not have to learn a second exception to stay correct.

    Carries the HTTP status. Callers that need to distinguish one failure from
    another — a delete finding nothing, say — get to ask a question with an
    answer, instead of searching the message for a number that is not in it.
    """

    def __init__(self, reason: str, *, status: int | None = None) -> None:
        super().__init__(reason)
        self.status = status


class SyncTokenExpired(Exception):
    """Google answered 410 for our sync token.

    Not an error in any meaningful sense — Google expires tokens on its own
    schedule and says so in the docs. The only correct response is to discard
    the token and re-read the window from scratch, which is why this is its own
    type rather than a status code the caller has to remember to special-case.
    """


@dataclass
class EventPage:
    events: list[dict] = field(default_factory=list)
    next_sync_token: str = ""


def _base() -> str:
    """The API root, overridable for tests."""
    return (config("GOOGLE_CALENDAR_API_BASE", default="").strip() or API_BASE).rstrip(
        "/"
    )


def _events_url() -> str:
    return f"{_base()}/calendars/{CALENDAR_ID}/events"


def _get(url: str, *, access_token: str, params: dict) -> dict:
    """GET and parse, translating Google's failures into ours.

    410 is separated out before anything else: it is the one status whose
    correct handling is "carry on differently" rather than "give up".
    """
    try:
        response = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise CalendarApiError(f"Could not reach Google Calendar: {type(exc).__name__}")

    if response.status_code == 410:
        raise SyncTokenExpired()

    try:
        body = response.json()
    except ValueError:
        raise CalendarApiError(
            f"Google Calendar returned a non-JSON response ({response.status_code})"
        )

    if not response.ok or not isinstance(body, dict):
        reason = "unknown"
        if isinstance(body, dict):
            error = body.get("error")
            # Google nests the useful string two different ways depending on
            # which front end answers.
            if isinstance(error, dict):
                reason = error.get("message") or error.get("status") or reason
            elif error:
                reason = str(error)
        # The status is logged, the token never is.
        logger.warning(
            "google calendar call failed: %s (%s)", reason, response.status_code
        )
        raise CalendarApiError(
            f"Google Calendar rejected the request: {reason}",
            status=response.status_code,
        )

    return body


def list_events(
    *,
    access_token: str,
    sync_token: str = "",
    time_min: datetime | None = None,
) -> EventPage:
    """Read events, incrementally when we have a cursor.

    With a sync token Google returns only what changed since it was issued —
    including deletions, as entries with ``status: cancelled``, which a date
    range would never show. Without one it returns everything from
    ``time_min``, and issues a token for next time.

    ``singleEvents`` expands recurrence into instances. The alternative is
    storing recurrence rules and evaluating them locally, which is a calendar
    engine and not what this story is.

    Raises :class:`SyncTokenExpired` if the cursor has aged out.
    """
    params: dict[str, object] = {
        "maxResults": PAGE_SIZE,
        "singleEvents": "true",
        "showDeleted": "true",
    }
    if sync_token:
        params["syncToken"] = sync_token
    else:
        # Only meaningful on a full read. Google rejects a request that sends
        # both a sync token and a time window.
        if time_min is not None:
            params["timeMin"] = time_min.isoformat().replace("+00:00", "Z")

    events: list[dict] = []
    page_token = ""
    for _ in range(MAX_PAGES):
        if page_token:
            params["pageToken"] = page_token
        body = _get(_events_url(), access_token=access_token, params=params)
        events.extend(body.get("items") or [])

        page_token = body.get("nextPageToken") or ""
        if not page_token:
            # Google sends the sync token only on the final page. Taking one
            # from an earlier page would acknowledge changes we had not read
            # and lose them permanently — the next incremental sync would
            # start after them.
            return EventPage(
                events=events, next_sync_token=body.get("nextSyncToken", "")
            )

    raise CalendarApiError(
        f"Google Calendar paginated past {MAX_PAGES} pages; refusing to continue"
    )


def event_instant(payload: dict | None) -> tuple[datetime | None, str]:
    """Read a Google start/end block into a UTC instant and an IANA zone.

    Google sends one of two shapes: ``dateTime`` with an offset for a timed
    event, and ``date`` for an all-day one. The zone arrives separately in
    ``timeZone`` and is the thing worth keeping — D-01 stores a zone rather
    than an offset precisely so a meeting survives a DST boundary, and
    discarding it here would put external events back on the footing that
    decision was made to avoid.
    """
    if not isinstance(payload, dict):
        return None, ""

    zone_name = str(payload.get("timeZone") or "")
    raw = payload.get("dateTime") or payload.get("date") or ""
    if not raw:
        return None, zone_name

    parsed = parse_datetime(raw)
    if parsed is None:
        # An all-day event's `date` is a plain date, which parse_datetime
        # declines. Midnight in the event's own zone is the honest reading.
        day = parse_date(raw)
        if day is None:
            return None, zone_name
        parsed = datetime(day.year, day.month, day.day)

    if timezone.is_naive(parsed):
        # Every value that leaves here is aware and in UTC.
        #
        # An all-day `date` carries no time and no offset, and the column is a
        # UTC instant. Handed over naive under USE_TZ, it is reinterpreted
        # against whatever the process timezone happens to be — so the stored
        # instant depends on the server, and an all-day event lands on the
        # wrong day for anyone far enough from it. The event's own zone is the
        # fact worth using; UTC is the only defensible fallback, because the
        # server's zone is not a fact about the event.
        parsed = parsed.replace(tzinfo=_zone(zone_name))

    return parsed.astimezone(dt_timezone.utc), zone_name


def _zone(name: str) -> ZoneInfo | dt_timezone:
    """The event's IANA zone, or UTC if Google did not name a usable one."""
    if not name:
        return dt_timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        # A zone this machine's database does not know. UTC beats guessing,
        # and beats raising out of a sync that has thousands of other events
        # to get through.
        logger.info("unknown calendar timezone %r; reading the instant as UTC", name)
        return dt_timezone.utc


def _send(
    method: str, url: str, *, access_token: str, body: dict | None = None
) -> dict:
    """POST/PATCH/DELETE with a JSON body, translating Google's failures.

    Separate from :func:`_get` because a write that 404s means something
    different from a read that does — see :func:`delete_event`.
    """
    try:
        response = requests.request(
            method,
            url,
            json=body,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise CalendarApiError(f"Could not reach Google Calendar: {type(exc).__name__}")

    if response.status_code == 204 or not (response.content or b"").strip():
        return {}

    try:
        parsed = response.json()
    except ValueError:
        if response.ok:
            return {}
        raise CalendarApiError(
            f"Google Calendar returned a non-JSON response ({response.status_code})"
        )

    if not response.ok or not isinstance(parsed, dict):
        reason = "unknown"
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict):
                reason = error.get("message") or error.get("status") or reason
            elif error:
                reason = str(error)
        logger.warning(
            "google calendar write failed: %s (%s)", reason, response.status_code
        )
        raise CalendarApiError(
            f"Google Calendar rejected the write: {reason}", status=response.status_code
        )

    return parsed


def insert_event(*, access_token: str, body: dict) -> dict:
    """Create an event and return it, including the id Google assigned."""
    return _send("POST", _events_url(), access_token=access_token, body=body)


def patch_event(*, access_token: str, event_id: str, body: dict) -> dict:
    """Update an existing event in place.

    PATCH rather than PUT: a full replace would drop every field this app does
    not model — the operator's own notes, conferencing links, reminders — on
    an event that lives in their personal calendar.
    """
    return _send(
        "PATCH",
        f"{_events_url()}/{event_id}",
        access_token=access_token,
        body=body,
    )


def delete_event(*, access_token: str, event_id: str) -> None:
    """Remove an event.

    A 404 or 410 is success: the goal state is "the event is not there", and
    it has been reached. Treating it as a failure would strand a cancelled
    meeting in a permanent retry loop against an event nobody can produce.
    """
    try:
        _send("DELETE", f"{_events_url()}/{event_id}", access_token=access_token)
    except CalendarApiError as exc:
        if exc.status in (404, 410):
            logger.info("delete found nothing to delete; the event was already gone")
            return
        raise
