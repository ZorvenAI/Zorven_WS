"""Meeting record models.

Imported at the foot of ``apps/onboarding/models.py`` so they register under
the ``onboarding_sessions`` app label, the same way the erasure models do.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from tenants.models import Tenant


class RecordStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ISSUED = "ISSUED", "Issued"
    PARTIALLY_SIGNED = "PARTIALLY_SIGNED", "Partially signed"
    COMPLETED = "COMPLETED", "Completed"
    DECLINED = "DECLINED", "Declined"
    VOIDED = "VOIDED", "Voided"
    EXPIRED = "EXPIRED", "Expired"


#: A record in one of these is finished: it will never change state again, and
#: a corrected record has to be a new version.
TERMINAL_RECORD_STATUSES = (
    RecordStatus.COMPLETED,
    RecordStatus.DECLINED,
    RecordStatus.VOIDED,
    RecordStatus.EXPIRED,
)

#: Terminal without having been completed — the only states a new version may
#: supersede. A completed record stands; a later meeting can change what was
#: agreed, but that is a new record, not a replacement.
SUPERSEDABLE_RECORD_STATUSES = (
    RecordStatus.DECLINED,
    RecordStatus.VOIDED,
    RecordStatus.EXPIRED,
)

#: Content is frozen from issue onwards. Only a DRAFT still follows the
#: recording it was made from.
FROZEN_RECORD_STATUSES = tuple(s for s in RecordStatus if s != RecordStatus.DRAFT)


class MeetingRecord(models.Model):
    """The signed record of one meeting.

    While DRAFT it has no content of its own: it is a view of the recording.
    Issuing copies everything into ``snapshot`` and fingerprints it, and from
    then on neither the snapshot nor the recording's description and
    transcript may change.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    session = models.ForeignKey(
        "onboarding_sessions.OnboardingSession",
        on_delete=models.CASCADE,
        related_name="meeting_records",
    )
    # CASCADE at the database level, with deletion of a recording that has an
    # issued record refused in the API. Holding issued records back from the
    # erasure and retention sweeps is a later step of the same plan; until
    # then erasure behaves as it always has.
    recording = models.ForeignKey(
        "onboarding_sessions.MeetingRecording",
        on_delete=models.CASCADE,
        related_name="meeting_records",
    )
    record_number = models.CharField(
        max_length=40,
        unique=True,
        help_text="Human-readable identifier, e.g. MR-000085-v1",
    )
    version = models.PositiveIntegerField(default=1)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_by",
        help_text="The earlier version this one replaces",
    )
    status = models.CharField(
        max_length=20,
        choices=RecordStatus.choices,
        default=RecordStatus.DRAFT,
        db_index=True,
    )
    snapshot = models.JSONField(
        null=True,
        blank=True,
        help_text="The frozen content. Null while DRAFT; set once, at issue.",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="SHA-256 of the canonical snapshot",
    )
    clause_version = models.CharField(max_length=40, blank=True, default="")
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_meeting_records",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True, default="")
    pdf_gcs_path = models.CharField(max_length=500, blank=True, default="")
    pdf_hash = models.CharField(max_length=64, blank=True, default="")
    legal_hold_until = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_meeting_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "onboarding_sessions"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["recording", "version"],
                name="unique_record_version_per_recording",
            ),
            # One record in play per meeting. Without it two operators could
            # each issue a different record for the same recording.
            models.UniqueConstraint(
                fields=["recording"],
                condition=~Q(status__in=["COMPLETED", "DECLINED", "VOIDED", "EXPIRED"]),
                name="one_open_record_per_recording",
            ),
        ]
        indexes = [models.Index(fields=["session", "status"])]

    def __str__(self) -> str:
        return f"{self.record_number} · {self.status}"

    @property
    def is_frozen(self) -> bool:
        return self.status != RecordStatus.DRAFT


class RecordEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    ISSUED = "ISSUED", "Issued"
    VOIDED = "VOIDED", "Voided"
    SUPERSEDED = "SUPERSEDED", "Superseded"
    DOWNLOADED = "DOWNLOADED", "Downloaded"


class RecordEventError(RuntimeError):
    """An attempt to rewrite or remove part of the audit trail."""


class RecordEvent(models.Model):
    """One entry in a record's audit trail.

    Insert-only. An audit trail that can be edited proves nothing, so the
    model refuses updates and deletes itself rather than relying on callers
    to remember.

    A deliberate exception to the repo's model convention: no ``created_at``
    or ``updated_at``. ``occurred_at`` is the creation time, and a row is
    never updated, so ``updated_at`` could only ever equal it. Ordered oldest
    first because an audit trail is read in the order things happened.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    record = models.ForeignKey(
        MeetingRecord, on_delete=models.CASCADE, related_name="events"
    )
    actor_user = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_record_events",
    )
    event_type = models.CharField(max_length=24, choices=RecordEventType.choices)
    detail = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "onboarding_sessions"
        ordering = ["occurred_at", "id"]
        indexes = [models.Index(fields=["record", "occurred_at"])]

    def __str__(self) -> str:
        return f"{self.event_type} · record {self.record_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RecordEventError("audit trail entries cannot be changed")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RecordEventError("audit trail entries cannot be deleted")
