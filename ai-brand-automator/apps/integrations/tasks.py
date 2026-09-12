"""Scheduled token refresh (D-02 AC-4).

The card is explicit that refresh is "a scheduled job, not lazy-on-use, so
that a stale grant surfaces as an actionable notification rather than as a
failed sync at the moment the operator needs it".

That distinction is the whole point. Refreshing lazily means the first person
to discover a revoked grant is the operator who just tried to use the
calendar, mid-task. Refreshing on a schedule means the connection is already
marked NEEDS_RECONNECT, and the pane says so before they need it.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.integrations import google_calendar
from apps.integrations.models import CalendarConnection, ConnectionStatus

logger = logging.getLogger(__name__)


@shared_task(name="integrations.refresh_calendar_tokens")
def refresh_calendar_tokens() -> dict[str, int]:
    """Refresh every live connection, marking the dead ones.

    Never raises: one tenant's revoked grant must not stop the sweep for
    everybody else, and a task that dies halfway leaves the connections it
    never reached looking healthy.
    """
    refreshed = failed = 0

    if not google_calendar.is_configured():
        # Abandon the sweep rather than run it. Without client credentials
        # every refresh comes back `invalid_client` — which is this deployment
        # being misconfigured, not any operator's grant being revoked — and the
        # loop below would mark every healthy calendar in the fleet
        # NEEDS_RECONNECT on the strength of it. A worker that lost the
        # credentials (they live only on the backend and the worker) must fail
        # loudly and change nothing.
        logger.error(
            "calendar_refresh_skipped_unconfigured",
            extra={"reason": "GOOGLE_OAUTH_CLIENT_ID/SECRET missing on this worker"},
        )
        return {"refreshed": 0, "needs_reconnect": 0, "skipped": "unconfigured"}

    for connection in CalendarConnection.objects.filter(
        status=ConnectionStatus.CONNECTED
    ).exclude(_refresh_token=""):
        token = connection.refresh_token
        if not token:
            continue
        try:
            google_calendar.refresh(refresh_token=token)
        except google_calendar.OAuthError as exc:
            # Marked, not deleted. The operator reconnects; deleting the row
            # would lose who connected it and when, which is the audit trail.
            connection.status = ConnectionStatus.NEEDS_RECONNECT
            connection.last_error = exc.reason[:255]
            connection.save(update_fields=["status", "last_error", "updated_at"])
            logger.warning(
                "calendar_connection_needs_reconnect",
                extra={
                    "tenant_id": connection.tenant_id,
                    "secret_path": connection.secret_path,
                    "reason": exc.reason,
                },
            )
            failed += 1
            continue

        connection.last_refreshed_at = timezone.now()
        connection.save(update_fields=["last_refreshed_at", "updated_at"])
        refreshed += 1

    return {"refreshed": refreshed, "needs_reconnect": failed}


@shared_task(name="integrations.sync_calendars")
def sync_calendars() -> dict[str, int]:
    """Pull every connected calendar (D-03 AC-1).

    Scheduled rather than lazy for the same reason the token refresh is: an
    external meeting the operator cannot see is indistinguishable from one that
    does not exist, and discovering it when they open the pane means the lag is
    however long the pane took to load.

    Never raises, and never lets one tenant's failure reach another's. AC-3 is
    explicit that the in-app calendar keeps working while Google does not.
    """
    from apps.integrations import sync

    if not google_calendar.is_configured():
        # Same hazard as the token refresh: without credentials every call
        # fails, and recording those failures would put the whole fleet into
        # backoff over one missing env var on one worker.
        logger.error(
            "calendar_sync_skipped_unconfigured",
            extra={"reason": "GOOGLE_OAUTH_CLIENT_ID/SECRET missing on this worker"},
        )
        return {"synced": 0, "failed": 0, "skipped": 0}

    synced = failed = skipped = 0
    for connection in CalendarConnection.objects.filter(
        status=ConnectionStatus.CONNECTED
    ).exclude(_refresh_token=""):
        if not sync.due(connection):
            # Backing off. Counted rather than silent, so a fleet stuck in
            # backoff is visible in the return value rather than looking idle.
            skipped += 1
            continue
        result = sync.pull_connection(connection)
        if "error" in result:
            failed += 1
        else:
            synced += 1

    return {"synced": synced, "failed": failed, "skipped": skipped}
