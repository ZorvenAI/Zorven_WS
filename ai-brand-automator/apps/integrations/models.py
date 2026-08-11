"""Tenant-owned provider connections (D-02, Design §19).

§19 is explicit that the agent never holds calendar credentials: "Calendar
sync is a Django concern; the agent reads scheduled meetings". That is the
point of the extra hop — the agent's blast radius excludes the operator's
personal calendar, and nothing here is ever transmitted to it.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from automation.encryption import decrypt_token, encrypt_token
from tenants.models import Tenant


class ConnectionStatus(models.TextChoices):
    CONNECTED = "CONNECTED", "Connected"
    #: The grant no longer works — revoked upstream, expired, or scope
    #: withdrawn. Distinct from disconnected so AC-4 can tell an operator to
    #: reconnect rather than silently going stale.
    NEEDS_RECONNECT = "NEEDS_RECONNECT", "Needs reconnect"
    DISCONNECTED = "DISCONNECTED", "Disconnected"


class CalendarConnection(models.Model):
    """One tenant's Google Calendar grant.

    §19 names the storage location as ``secrets/<tenant_id>/google_calendar``.
    That is honoured as a **logical key** — see :attr:`secret_path` — rather
    than a filesystem path or a per-tenant GCP Secret Manager entry. Secret
    Manager charges per secret *version* and adds an IAM surface per tenant
    for something Fernet already covers, and this project already encrypts
    OAuth refresh tokens exactly this way in ``automation.SocialAccount``.

    The token itself lives in ``_refresh_token`` and is only reachable through
    the property, which is the pattern the root CLAUDE.md documents. Nothing
    reads the column directly.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="calendar_connections",
        help_text="Non-null: a connection belongs to somebody, always",
    )
    provider = models.CharField(max_length=32, default="google_calendar")

    #: Encrypted at rest with Fernet, keyed off SECRET_KEY
    #: (automation/encryption.py). Never logged, never serialised, never sent
    #: to the agent — see tests/test_secrets.py.
    _refresh_token = models.TextField(blank=True, default="", db_column="refresh_token")
    scope = models.CharField(
        max_length=255,
        default="https://www.googleapis.com/auth/calendar.events",
        help_text=(
            "The narrowest scope that supports read plus event creation, per "
            "the card: calendar.events, not calendar. A full-calendar grant "
            "would let this app delete an operator's personal appointments."
        ),
    )

    google_account_email = models.EmailField(blank=True, default="")
    status = models.CharField(
        max_length=24,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.CONNECTED,
        db_index=True,
    )
    #: Why it needs reconnecting, for AC-4's "specific reconnect prompt".
    last_error = models.CharField(max_length=255, blank=True, default="")

    connected_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calendar_connections",
    )
    connected_at = models.DateTimeField(auto_now_add=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-connected_at"]
        constraints = [
            # One live connection per tenant per provider. A second would make
            # "which calendar are we syncing" unanswerable, and D-03 would
            # have to pick one.
            models.UniqueConstraint(
                fields=["tenant", "provider"],
                condition=~Q(status="DISCONNECTED"),
                name="one_live_calendar_connection_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        # Deliberately no token material, not even a length: __str__ lands in
        # admin pages, shell transcripts and error reports.
        return f"{self.provider} for tenant {self.tenant_id} ({self.status})"

    @property
    def secret_path(self) -> str:
        """§19's ``secrets/<tenant_id>/google_calendar``.

        A logical name for the secret this row holds, not a location. Kept as
        a property so the design's vocabulary appears in the code and in audit
        events, and so a later move to a real secret store has an obvious
        seam.
        """
        return f"secrets/{self.tenant_id}/{self.provider}"

    @property
    def refresh_token(self) -> str | None:
        return decrypt_token(self._refresh_token) if self._refresh_token else None

    @refresh_token.setter
    def refresh_token(self, value: str | None) -> None:
        self._refresh_token = encrypt_token(value) if value else ""

    @property
    def is_usable(self) -> bool:
        return self.status == ConnectionStatus.CONNECTED and bool(self._refresh_token)
