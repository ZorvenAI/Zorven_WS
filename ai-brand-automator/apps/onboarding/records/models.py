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


class SignatoryParty(models.TextChoices):
    AGENCY = "AGENCY", "Agency"
    CLIENT = "CLIENT", "Client"


class SignatoryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SIGNED = "SIGNED", "Signed"
    DECLINED = "DECLINED", "Declined"


class SigningMethod(models.TextChoices):
    #: Emailed single-use link, then a one-time code sent to the same address.
    EMAIL_CODE = "EMAIL_CODE", "Emailed link and one-time code"
    #: Signed while logged in to the workspace.
    ACCOUNT = "ACCOUNT", "Signed in to the workspace"


class RecordSignatory(models.Model):
    """One person who signs a record, and the evidence that they did.

    Secrets are never stored: the link token, the one-time code and the
    signing session are each kept only as a hash, so a copy of this table
    cannot be used to sign anything.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    record = models.ForeignKey(
        MeetingRecord, on_delete=models.CASCADE, related_name="signatories"
    )
    party = models.CharField(max_length=8, choices=SignatoryParty.choices)
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField()
    required = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=10,
        choices=SignatoryStatus.choices,
        default=SignatoryStatus.PENDING,
    )

    # The emailed link.
    token_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    # The one-time code sent once the link is opened.
    code_hash = models.CharField(max_length=64, blank=True, default="")
    code_expires_at = models.DateTimeField(null=True, blank=True)
    code_sent_at = models.DateTimeField(null=True, blank=True)
    code_attempts = models.PositiveSmallIntegerField(default=0)
    # The short-lived session a correct code opens.
    session_hash = models.CharField(max_length=64, blank=True, default="")
    session_expires_at = models.DateTimeField(null=True, blank=True)

    # What they did.
    signed_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    method = models.CharField(
        max_length=12, choices=SigningMethod.choices, blank=True, default=""
    )
    typed_name = models.CharField(max_length=255, blank=True, default="")
    remarks = models.TextField(blank=True, default="")
    decline_reason = models.TextField(blank=True, default="")
    #: When this signatory last accepted the other signatories' remarks.
    remarks_acknowledged_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=40, blank=True, default="")
    #: The fingerprint that was on screen when they acted.
    content_hash = models.CharField(max_length=64, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "onboarding_sessions"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["record", "email"], name="unique_signatory_email_per_record"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.party}) · {self.status}"


class RecordEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    ISSUED = "ISSUED", "Issued"
    VOIDED = "VOIDED", "Voided"
    SUPERSEDED = "SUPERSEDED", "Superseded"
    DOWNLOADED = "DOWNLOADED", "Downloaded"
    EMAIL_SENT = "EMAIL_SENT", "Email sent"
    EMAIL_FAILED = "EMAIL_FAILED", "Email failed"
    VIEWED = "VIEWED", "Signing link opened"
    CODE_SENT = "CODE_SENT", "One-time code sent"
    CODE_VERIFIED = "CODE_VERIFIED", "One-time code verified"
    CODE_FAILED = "CODE_FAILED", "One-time code rejected"
    SIGNED = "SIGNED", "Signed"
    REMARKS_ACKNOWLEDGED = "REMARKS_ACKNOWLEDGED", "Remarks acknowledged"
    DECLINED = "DECLINED", "Declined"
    COMPLETED = "COMPLETED", "Completed"
    EXPIRED = "EXPIRED", "Expired"
    REMINDED = "REMINDED", "Reminder sent"


class RecordEventError(RuntimeError):
    """An attempt to rewrite or remove part of the audit trail."""


class RecordEvent(models.Model):
    """One entry in a record's audit trail.

    Insert-only. An audit trail that can be edited proves nothing, so the
    model refuses updates and deletes itself rather than relying on callers
    to remember.
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
    signatory = models.ForeignKey(
        RecordSignatory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
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
