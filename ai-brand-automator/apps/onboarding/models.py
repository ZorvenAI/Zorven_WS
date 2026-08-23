"""Core session models for the Onboarding Intelligence Agent (Design §10.1).

Three models, all additive: OnboardingSession, Questionnaire and Question.
Nothing here alters an existing table, and every field is either nullable or
carries a default, so the migration is safe on a populated database
(NFR-COMPAT).

Two invariants are enforced at the database and model layers rather than in a
serializer, because the agent is not the only writer:

- **One live session per company** is a partial unique index, so a second
  non-terminal session fails on insert rather than on an application check
  that a management command or a shell session could bypass (§9.4, AC-2).
- **A sufficiency score without evidence is refused** in ``Question.save()``.
  OG-06 says a green signal must carry its supporting spans; a score written
  without them is an unsourced claim the UI would render as a green tick.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from tenants.models import Tenant


class SessionStatus(models.TextChoices):
    """The §9.4 state machine.

    Transitions are validated in B-04's ``services/session_state.py``; this
    enum is the set it validates against, so the values are taken verbatim
    from the state diagram and no intermediate value is invented.

    ``ARCHIVED`` is the one addition. B-01's technical note lists ten statuses
    and forbids inventing values, but AC-2 and §9.4 both define the terminal
    set as (COMPLETED, ARCHIVED) — the partial unique index below cannot be
    expressed without it. It is a terminal state the same card depends on, not
    an invented intermediate.
    """

    DRAFT = "DRAFT", "Draft"
    PREPARING = "PREPARING", "Preparing"
    READY = "READY", "Ready"
    MEETING_LIVE = "MEETING_LIVE", "Meeting live"
    GATHERED = "GATHERED", "Gathered"
    PROCESSING = "PROCESSING", "Processing"
    REVIEW_PENDING = "REVIEW_PENDING", "Review pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    COMPLETED = "COMPLETED", "Completed"
    ESCALATED = "ESCALATED", "Escalated"
    ARCHIVED = "ARCHIVED", "Archived"


#: A company may hold one session in any status outside this set (§9.4).
TERMINAL_STATUSES = (SessionStatus.COMPLETED, SessionStatus.ARCHIVED)


def tenant_scope_q(tenant: Tenant | None, field: str = "tenant") -> Q:
    """The project's tenant predicate, defined once.

    Pre-tenant rows (``tenant IS NULL``) stay visible: they predate
    multi-tenancy and would otherwise vanish from a tenant's view after an
    upgrade. ``field`` lets a caller scope through a relation — Question has
    no tenant column of its own and is reached via
    ``questionnaire__tenant``.

    Both the manager and the admin use this. They drifted apart when each
    wrote its own filter, and the admin's copy silently dropped the
    pre-tenant half.
    """
    if tenant is None:
        return Q(**{f"{field}__isnull": True})
    return Q(**{field: tenant}) | Q(**{f"{field}__isnull": True})


class TenantScopedManager(models.Manager):
    """Manager with an explicit tenant filter.

    B-01's technical note is blunt: "a manager that does not filter by tenant
    is the single most likely source of a cross-tenant leak, and
    RoleBasedPermissionMixin will not save you at the ORM layer." The filter
    is a method rather than an override of ``get_queryset`` so that admin and
    migrations still see every row, while any caller serving a request has to
    say which tenant it means.
    """

    def for_tenant(self, tenant: Tenant | None) -> models.QuerySet:
        """Rows for one tenant, plus pre-tenant rows.

        Mirrors the fleet's defensive pattern: tenant-less rows predate
        multi-tenancy and stay visible, rather than vanishing from a tenant's
        view after an upgrade.
        """
        return self.get_queryset().filter(tenant_scope_q(tenant))


class OnboardingSession(models.Model):
    """One prepare-and-meet cycle for a company (Design §10.1, §9.4)."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
        help_text="Tenant (nullable for pre-tenant rows)",
    )
    company = models.ForeignKey(
        "onboarding.Company",
        on_delete=models.CASCADE,
        related_name="onboarding_sessions",
        help_text="The company being onboarded",
    )
    status = models.CharField(
        max_length=32,
        choices=SessionStatus.choices,
        default=SessionStatus.DRAFT,
        db_index=True,
    )
    escalated_from = models.CharField(
        max_length=32,
        choices=SessionStatus.choices,
        null=True,
        blank=True,
        help_text=(
            "Status held before escalation, restored on resolution. Without "
            "it the agent would have to guess, and guessing wrong strands "
            "the session (§9.4)."
        ),
    )
    questionnaire = models.ForeignKey(
        "onboarding_sessions.Questionnaire",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pinned_to_sessions",
    )
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarding_sessions",
    )
    prompt_versions = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "{prompt_name: version} pinned once at session start. §17.2 makes "
            "this the mechanism that stops a mid-meeting POI promotion from "
            "changing behaviour. Written by L-03."
        ),
    )
    evidence_manifest_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Half of the PROCESS idempotency key (§9.3)",
    )
    process_job_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="OIA job id from the most recent PROCESS dispatch",
    )
    process_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Terminal callback summary from OIA (§10.2.2)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # AC-2: a database property, not application logic. A second
            # non-terminal session for the same company fails on insert.
            models.UniqueConstraint(
                fields=["company"],
                condition=~Q(status__in=TERMINAL_STATUSES),
                name="unique_active_session_per_company",
            )
        ]
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self) -> str:
        return f"Session {self.pk} · company {self.company_id} · {self.status}"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class QuestionnaireStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    APPROVED = "APPROVED", "Approved"


class Questionnaire(models.Model):
    """The prepared question set for a session (Design §10.1)."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    company = models.ForeignKey(
        "onboarding.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="questionnaires",
        help_text=(
            "Nullable because preparation precedes onboarding. C-01 routes a "
            "prep turn with no session, C-02 stores a research brief keyed on "
            "a business name rather than a Company, and C-03 generates a "
            "questionnaire from that brief — none of which require the "
            "company to exist yet. Requiring it here would make the epic's "
            "normal path unstorable. Attached once a Company is created."
        ),
    )
    session = models.ForeignKey(
        OnboardingSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="questionnaires",
    )
    status = models.CharField(
        max_length=16,
        choices=QuestionnaireStatus.choices,
        default=QuestionnaireStatus.DRAFT,
        db_index=True,
    )
    depth = models.PositiveSmallIntegerField(
        default=3, help_text="Requested depth, 1-5"
    )
    question_count = models.PositiveIntegerField(default=0)
    source_chat_session_id = models.CharField(max_length=64, blank=True, default="")
    approved_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_questionnaires",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Approval freezes the version; further edits create version+1 in "
            "DRAFT rather than mutating an approved set."
        ),
    )
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_by",
        help_text=(
            "The version this one replaces (C-04 AC-3). Makes the chain "
            "explicit rather than implied by a version number: the card "
            "requires the approved version to survive intact, and the "
            "evidence spans on Question point at a specific version's rows."
        ),
    )
    is_template = models.BooleanField(
        default=False,
        help_text="Reusable for another company in the same tenant (D-05)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # At most one DRAFT per company, so two concurrent edits of an
            # approved set cannot both create version n+1.
            #
            # **This does not cover the common case, and that is deliberate
            # rather than overlooked.** company is nullable — prep precedes
            # onboarding, which is why C-03 made it so — and PostgreSQL treats
            # NULLs as distinct, so nothing is enforced while a questionnaire
            # has no company. The real protection is select_for_update() on
            # the row being superseded, which works regardless. This
            # constraint is defence for the case where it can apply, not the
            # mechanism.
            models.UniqueConstraint(
                fields=["tenant", "company"],
                condition=Q(status="DRAFT")
                & Q(company__isnull=False)
                & Q(tenant__isnull=False),
                name="one_draft_questionnaire_per_company",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self) -> str:
        return f"Questionnaire {self.pk} v{self.version} · {self.status}"


class QuestionOrigin(models.TextChoices):
    PREPARED = "PREPARED", "Prepared"
    ADHOC = "ADHOC", "Ad hoc"
    FOLLOWUP = "FOLLOWUP", "Follow-up"


class WorkflowTarget(models.TextChoices):
    WF1 = "WF1", "WF1"
    WF2 = "WF2", "WF2"
    WF3 = "WF3", "WF3"


class QuestionStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    GREEN = "GREEN", "Green"
    SKIPPED = "SKIPPED", "Skipped"


class Question(models.Model):
    """One question on the checklist (Design §10.1).

    The checkbox the operator sees is derived from ``status``; it is not a
    separate field, so the two cannot disagree.
    """

    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.CASCADE, related_name="questions"
    )
    order = models.PositiveIntegerField(default=0)
    text = models.TextField()
    origin = models.CharField(
        max_length=16,
        choices=QuestionOrigin.choices,
        default=QuestionOrigin.PREPARED,
    )
    workflow_target = models.CharField(
        max_length=8, choices=WorkflowTarget.choices, default=WorkflowTarget.WF1
    )
    target_field = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Join to FieldProvenance (B-05)",
    )
    status = models.CharField(
        max_length=16,
        choices=QuestionStatus.choices,
        default=QuestionStatus.OPEN,
        db_index=True,
    )
    sufficiency_score = models.FloatField(null=True, blank=True)
    answer_summary = models.TextField(blank=True, default="")
    evidence = models.JSONField(
        default=list,
        blank=True,
        help_text="[{recording_id, t_start, t_end}] backing the score",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["questionnaire_id", "order"]
        indexes = [models.Index(fields=["questionnaire", "status"])]

    def __str__(self) -> str:
        return f"Q{self.order} · {self.status} · {self.text[:40]}"

    def clean(self) -> None:
        """OG-06: a score and its evidence are written together or not at all.

        Enforced here as well as in the serializer because the agent is not
        the only writer — a shell session, a data fix or a later story can all
        reach the model directly.
        """
        super().clean()
        has_score = self.sufficiency_score is not None
        has_evidence = bool(self.evidence)

        if has_score and not has_evidence:
            raise ValidationError(
                {
                    "evidence": (
                        "A sufficiency_score requires at least one evidence "
                        "span (OG-06). A score without evidence is an "
                        "unsourced claim."
                    )
                }
            )
        if has_evidence and not has_score:
            raise ValidationError(
                {
                    "sufficiency_score": (
                        "Evidence requires the sufficiency_score it supports "
                        "(OG-06)."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False)
        return super().save(*args, **kwargs)


class RecordingModality(models.TextChoices):
    """§24: video is declared in v1 so adding it in v2 is a data-free change.

    ``VIDEO`` is deliberately reachable — no constraint, validator or
    serializer rejects it (AC-2). A choice that cannot be selected would not
    prove the migration-free claim §24 makes; it would only look like it did.
    """

    AUDIO = "AUDIO", "Audio"
    VIDEO = "VIDEO", "Video"


class RecordingStatus(models.TextChoices):
    RECORDING = "RECORDING", "Recording"
    UPLOADED = "UPLOADED", "Uploaded"
    TRANSCRIBED = "TRANSCRIBED", "Transcribed"
    SUMMARIZED = "SUMMARIZED", "Summarized"
    FAILED = "FAILED", "Failed"


class MeetingRecording(models.Model):
    """One start/stop cycle of a meeting recording (Design §10.1).

    A cycle, not a meeting: an operator who starts and stops three times gets
    three rows, each with its own duration and status, all pointing at the one
    session (AC-1). Modelling it per meeting would lose the pause structure and
    make a failed segment indistinguishable from a short one.

    ``audio_asset`` is a FK to BrandAsset rather than a raw GCS path. That is
    deliberate per the card: recordings inherit the existing landing-bucket,
    Kafka and RAG pipeline instead of growing a parallel one.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    session = models.ForeignKey(
        OnboardingSession,
        on_delete=models.CASCADE,
        related_name="recordings",
    )
    modality = models.CharField(
        max_length=8,
        choices=RecordingModality.choices,
        default=RecordingModality.AUDIO,
        help_text="AUDIO in v1; VIDEO reserved and unconstrained (§24)",
    )
    audio_asset = models.ForeignKey(
        "onboarding.BrandAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_recordings",
        help_text=(
            "The uploaded audio, as a BrandAsset so it rides the existing "
            "ingestion pipeline. Null until the upload completes."
        ),
    )
    transcript_gcs_path = models.CharField(max_length=500, blank=True, default="")

    # ── Resumable upload (F-03) ──────────────────────────────────────
    #
    # AC-1: "the upload session id is persisted so a process restart can
    # resume rather than restart". A resumable session is addressed by a URL
    # GCS issues once; losing it means the bytes already accepted are
    # unreachable and the operator re-uploads a meeting they already gave us.
    #
    # The URL carries its own authorisation, so it is a credential with a
    # short life. It is never logged and never leaves this row except to the
    # browser that is uploading — see the serializer, which does not expose it.
    upload_session_url = models.TextField(blank=True, default="")

    #: Where the object lands. Held separately from the session URL because
    #: the path outlives the session: finalisation registers a BrandAsset
    #: against it after the session is spent.
    upload_gcs_path = models.CharField(max_length=500, blank=True, default="")

    #: Guards AC-4's replay rule. A second finalisation carrying the key that
    #: already finalised this row is answered from the row rather than
    #: creating a second BrandAsset for one recording.
    finalise_key = models.CharField(max_length=128, blank=True, default="")
    duration_s = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Whole seconds; null while still RECORDING",
    )
    status = models.CharField(
        max_length=16,
        choices=RecordingStatus.choices,
        default=RecordingStatus.RECORDING,
        db_index=True,
    )
    summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="{text, key_moments: [{t, label}]} — written by a later story",
    )
    transcript = models.JSONField(
        default=list,
        blank=True,
        help_text="[{text, speaker, t_start, t_end, redaction_applied}]",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["session", "status"]),
            models.Index(fields=["tenant", "status"]),
            # For M-05's stuck-session sweeper (AC-4): "every recording still
            # RECORDING that started before X". Added here rather than there
            # because the query shape is a property of this table, and an
            # index arriving with the sweeper would mean the first run scans.
            models.Index(fields=["status", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"Recording {self.pk} · session {self.session_id} · {self.status}"


class ConsentMethod(models.TextChoices):
    VERBAL_RECORDED = "VERBAL_RECORDED", "Verbal, recorded"
    CHECKBOX = "CHECKBOX", "Checkbox"


class ConsentRecord(models.Model):
    """Consent as a record rather than a boolean (Design §10.1, IG-08).

    A boolean answers "may we record?" but not "who agreed, to what, how, and
    is it still true?" — which is what an auditor and the erasure workflow both
    need. IG-08 reads this row, so every one of subject, method, scope and
    grantor is persisted (AC-3).

    ``granted_at`` is server-set and never client-supplied: FR-REC-01 is
    explicit, and a client-chosen consent timestamp is exactly the field an
    incident would turn on.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    session = models.ForeignKey(
        OnboardingSession,
        on_delete=models.CASCADE,
        related_name="consent_records",
    )
    subject_name = models.CharField(
        max_length=255, help_text="The person consenting to be recorded"
    )
    granted_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_consents",
        help_text="The operator who captured the consent",
    )
    method = models.CharField(
        max_length=20,
        choices=ConsentMethod.choices,
        default=ConsentMethod.VERBAL_RECORDED,
    )
    scope = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "What was consented to. No schema enforced here — the consent API "
            "story owns that contract."
        ),
    )
    granted_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Server-set (FR-REC-01); never accepted from a client",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Set on revocation. Visible to any consumer querying the session's "
            "consent state; triggers erasure in a later story, not this one."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        ordering = ["-granted_at"]
        indexes = [models.Index(fields=["session", "revoked_at"])]

    def __str__(self) -> str:
        state = "revoked" if self.revoked_at else "active"
        return f"Consent {self.pk} · {self.subject_name} · {state}"

    @property
    def is_active(self) -> bool:
        """Consent state as one expression, so consumers cannot disagree."""
        return self.revoked_at is None


class FieldClassification(models.TextChoices):
    """D-04: KEY fields gate the review, SECONDARY ones do not."""

    KEY = "KEY", "Key"
    SECONDARY = "SECONDARY", "Secondary"


class ProvenanceStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    EDITED = "EDITED", "Edited"
    CONFLICT = "CONFLICT", "Conflict"


#: Statuses a PROCESS re-run must never overwrite (PG-06).
PROTECTED_STATUSES = (ProvenanceStatus.CONFIRMED, ProvenanceStatus.EDITED)


class FieldProvenance(models.Model):
    """Where a written field value came from (Design §10.1, §5.3 OG-01).

    §10.1 calls the check constraint below "the most important line in this
    section", and the reason is worth restating: OG-01 drops ungrounded values
    inside the agent, which is the right place for it, but the agent is not
    the only writer. A migration, a data fix, a refactor or a bug can all
    insert a row. The constraint makes those writes fail in PostgreSQL rather
    than relying on every future writer to behave.

    That is also why the rule is **not** in ``save()``: ``bulk_create()``
    bypasses ``save()``, and J-03 writes provenance in bulk (§8.2) — exactly
    the path that would otherwise slip through.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    session = models.ForeignKey(
        OnboardingSession,
        on_delete=models.CASCADE,
        related_name="provenance",
    )

    model_name = models.CharField(
        max_length=64, help_text="The Django model written to, e.g. 'Company'"
    )
    field_name = models.CharField(max_length=128)

    # JSON rather than text so a value round-trips losslessly. Six of the
    # thirteen B-03 Company fields are JSON-typed, and storing those as text
    # would make the provenance record and the value it describes disagree
    # about their own shape.
    extracted_value = models.JSONField(
        help_text="What the agent proposed, in the shape it will be written"
    )
    final_value = models.JSONField(
        null=True,
        blank=True,
        help_text="What a reviewer confirmed or edited it to; null until then",
    )

    classification = models.CharField(
        max_length=16,
        choices=FieldClassification.choices,
        default=FieldClassification.SECONDARY,
    )
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="0.000-1.000, bounded by its own constraint. Null before scoring.",
    )

    # ── The three sources, at least one of which must be present ──────
    source_recording = models.ForeignKey(
        MeetingRecording,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provenance",
    )
    source_span = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "{recording_id, t_start, t_end} — the same shape as "
            "Question.evidence, so K-01 can seek a player from either."
        ),
    )
    source_media = models.ForeignKey(
        "onboarding.BrandAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provenance",
    )

    status = models.CharField(
        max_length=16,
        choices=ProvenanceStatus.choices,
        default=ProvenanceStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_provenance",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        ordering = ["model_name", "field_name"]
        indexes = [
            models.Index(fields=["session", "status"]),
            models.Index(fields=["tenant", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "model_name", "field_name"],
                name="unique_provenance_per_field",
            ),
            # OG-01, as a property of the database. Every write path — the
            # ORM, bulk_create, raw SQL and a data migration — hits this.
            models.CheckConstraint(
                check=(
                    Q(source_recording__isnull=False)
                    | Q(source_span__isnull=False)
                    | Q(source_media__isnull=False)
                ),
                name="provenance_requires_a_source",
            ),
            # Cheap here, annoying to add once rows exist.
            models.CheckConstraint(
                check=Q(confidence__isnull=True)
                | (Q(confidence__gte=0) & Q(confidence__lte=1)),
                name="confidence_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.model_name}.{self.field_name} · {self.status}"

    @property
    def is_protected(self) -> bool:
        """True when PG-06 forbids a re-run from overwriting this row."""
        return self.status in PROTECTED_STATUSES

    @property
    def has_source(self) -> bool:
        """The Python-side reading of the constraint, for callers that want
        to check before writing rather than catch an IntegrityError.

        ``is not None`` rather than truthiness, because the constraint asks
        ``IS NOT NULL``. An empty ``source_span`` — ``{}`` or ``[]`` — is
        grounded as far as PostgreSQL is concerned, and a truthy test called
        it ungrounded. Two readings of one rule that disagree is exactly what
        putting the rule in the database was meant to avoid.

        This does mean an empty span counts, which is faithful to the
        constraint but arguably too permissive as provenance. Tightening that
        means tightening the constraint, which the B-05 card specifies
        verbatim — so it belongs in a follow-up, not in a property whose job
        is to mirror it.
        """
        return (
            self.source_recording_id is not None
            or self.source_span is not None
            or self.source_media_id is not None
        )


class ResearchBrief(models.Model):
    """A BusinessResearchBrief from SKL-OIA-01 (Design §8.1, story C-02).

    AC-2 requires the brief to survive the conversation: "when the operator
    returns to the conversation later, **or opens the Onboarding Interface**,
    the same brief is available without re-running research". The agent also
    caches briefs in Redis for an hour, which covers a tuning session — but a
    TTL'd cache cannot serve the Interface, and a re-run costs paid Tavily
    calls. This is the durable copy.

    **Keyed on the normalised business name, not on a session.** Prep starts
    before an ``OnboardingSession`` exists — that is the whole point of
    preparing in the chat the operator already uses — so a required session FK
    would make the common case unstorable. The session is attached when one
    exists, which is what makes the brief reachable from the Interface.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    session = models.ForeignKey(
        OnboardingSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="research_briefs",
        help_text="Attached once a session exists; prep can precede one",
    )

    company_name = models.CharField(
        max_length=255, help_text="As the operator typed it"
    )
    normalised_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text=(
            "Lower-cased, punctuation and legal suffixes stripped — the same "
            "normalisation the agent's Redis cache key uses, so the two "
            "layers agree on what counts as the same business"
        ),
    )

    # JSON, for the reason B-05 chose it for provenance values: the brief is a
    # nested structure (facts with sources, digital presence, unknowns) and
    # flattening it into columns would make this row and the agent's own model
    # disagree about their shape on every future field.
    brief = models.JSONField(help_text="The full BusinessResearchBrief payload")

    # Denormalised out of the JSON because operators and dashboards filter on
    # them, and a JSON containment query for "show me the thin briefs" is both
    # slower and easier to get wrong.
    degraded = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when research could not run (AC-3)",
    )
    degraded_reason = models.CharField(max_length=255, blank=True, default="")
    fact_count = models.PositiveIntegerField(default=0)
    unknown_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # One current brief per business per tenant. Re-running research
            # updates in place rather than accumulating versions: the backlog
            # asks for no versioning here, and inventing one would put a
            # second, differently-shaped history next to Questionnaire's.
            #
            # Two constraints rather than one, because PostgreSQL treats NULLs
            # as distinct — a single constraint over a nullable tenant would
            # silently permit unlimited duplicate pre-tenant rows, which is
            # exactly the case that would slip through review.
            models.UniqueConstraint(
                fields=["tenant", "normalised_name"],
                condition=Q(tenant__isnull=False),
                name="unique_brief_per_business_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["normalised_name"],
                condition=Q(tenant__isnull=True),
                name="unique_brief_per_business_without_tenant",
            ),
            models.CheckConstraint(
                check=Q(degraded=False) | ~Q(degraded_reason=""),
                name="degraded_brief_states_its_reason",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "normalised_name"])]

    def __str__(self) -> str:
        return f"{self.company_name} ({self.fact_count} facts)"


#: Named depths, mapped onto the 1-5 scale B-01 chose for
#: ``Questionnaire.depth`` (C-03, D2).
#:
#: The C-03 card and FR-PREP-04 talk in names — "12 questions at standard
#: depth", "the same request at deep" — while the column is an integer. Mapping
#: rather than changing the column keeps B-01's deliberate scale and gives the
#: chat surface the vocabulary its operators actually use. Defined here, beside
#: the field, so the agent and the API cannot disagree about what "deep" means.
DEPTH_NAMES = {"quick": 1, "standard": 3, "deep": 5}
DEFAULT_DEPTH = DEPTH_NAMES["standard"]


def depth_from(value: object) -> int:
    """Resolve a named or numeric depth to the stored 1-5 integer.

    Accepts either because the chat says "deep" and a programmatic caller says
    5. An unrecognised value falls back to standard rather than raising:
    preparation with a slightly wrong research budget beats no preparation,
    and the operator can regenerate.
    """
    if isinstance(value, str):
        return DEPTH_NAMES.get(value.strip().lower(), DEFAULT_DEPTH)
    if isinstance(value, bool):
        return DEFAULT_DEPTH
    if isinstance(value, int) and 1 <= value <= 5:
        return value
    return DEFAULT_DEPTH


class MeetingStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    CANCELLED = "CANCELLED", "Cancelled"


class MeetingOrigin(models.TextChoices):
    """Who owns a calendar entry, which is what makes D-03 AC-4 decidable.

    The rule is "in-app wins for onboarding-owned events; Google wins for
    externally created ones". That is answerable only if ownership is a fact
    on the row rather than something inferred from which fields happen to be
    filled in.
    """

    APP = "APP", "Created in the app"
    GOOGLE = "GOOGLE", "Created in Google Calendar"


class ScheduledMeeting(models.Model):
    """An onboarding meeting on the in-app calendar (D-01, Design §11).

    Separate from OnboardingSession rather than a pair of columns on it, for
    two reasons. AC-1 says cancelling *releases* the session, which needs a
    record to cancel rather than two fields to null — otherwise the fact that a
    meeting was ever booked disappears with it. And D-03's two-way sync needs a
    provider event id, which is a property of a calendar entry and has no
    business on a session.

    Not to be confused with ``automation.ContentCalendar``, which schedules
    social posts.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    #: Nullable since D-03. A meeting created in Google Calendar has no
    #: onboarding session and never will — it is somebody's dentist
    #: appointment that happens to share the operator's calendar. §11 asks for
    #: those to appear "read-only alongside in-app ones so the operator has a
    #: single view", and §10.2 names a single endpoint, so they share this
    #: table rather than sitting in one of their own and being merged on every
    #: read.
    #:
    #: The partial unique on `session` is unaffected: Postgres treats NULLs as
    #: distinct, so any number of external meetings can be SCHEDULED at once.
    session = models.ForeignKey(
        OnboardingSession,
        on_delete=models.CASCADE,
        related_name="meetings",
        null=True,
        blank=True,
    )
    origin = models.CharField(
        max_length=8,
        choices=MeetingOrigin.choices,
        default=MeetingOrigin.APP,
        db_index=True,
        help_text=(
            "APP entries are editable here and pushed outward. GOOGLE entries "
            "are read-only here — the viewset refuses writes to them — because "
            "this app is not the system of record for somebody's own diary."
        ),
    )

    # ── The instant, and where it was meant to happen ────────────────
    #
    # Stored as UTC plus an IANA zone name, never an offset. The card is blunt
    # about why: offset-storing "surfaces twice a year, in production, on a
    # customer call". An offset is a fact about one moment; a zone is a rule,
    # and only the rule survives a daylight-saving boundary.
    starts_at = models.DateTimeField(help_text="The instant the meeting begins, in UTC")
    ends_at = models.DateTimeField(help_text="The instant it ends, in UTC")
    timezone = models.CharField(
        max_length=64,
        help_text=(
            "IANA zone the meeting was scheduled in, e.g. 'Europe/London'. "
            "Kept alongside the UTC instant so a rescheduled or recurring "
            "meeting lands at the same *local* time across a DST change."
        ),
    )

    organiser = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarding_meetings",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=MeetingStatus.choices,
        default=MeetingStatus.SCHEDULED,
        db_index=True,
    )

    #: D-03 writes this. Present from the start so two-way sync does not need
    #: a migration to begin, and **empty** until then — a blank CharField
    #: rather than null, matching the rest of this app and keeping "no
    #: provider event" a single value instead of two.
    provider_event_id = models.CharField(max_length=255, blank=True, default="")

    #: Google's own `updated` stamp for the event, as of the last pull. AC-4
    #: needs to know whether the remote copy moved since we last looked, and
    #: our `updated_at` cannot answer that — it changes when *we* write.
    provider_updated_at = models.DateTimeField(null=True, blank=True)

    #: When this meeting was last pushed outward. Compared against
    #: ``updated_at`` to decide whether there is anything to push.
    #:
    #: Written with ``QuerySet.update()``, never ``save()``, precisely because
    #: ``updated_at`` is ``auto_now``: saving would bump the very field the
    #: comparison uses and every meeting would look dirty forever, patching
    #: itself on every cycle. ``updated_at`` therefore keeps meaning "last
    #: edited", not "last touched by sync".
    #:
    #: Null means "never pushed, or pushed and since invalidated" — the second
    #: is how a detected conflict asks to be re-pushed.
    provider_synced_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        ordering = ["starts_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(ends_at__gt=F("starts_at")),
                name="meeting_ends_after_it_starts",
            ),
            # The rule the card names, in the database: not an offset.
            #
            # This asks the narrow question deliberately. An earlier version
            # allow-listed what an IANA name looks like — a slash, or "UTC" —
            # and rejected 44 real zones in the process, including EST5EDT,
            # GMT, CET and Eire. The serializer accepted those (zoneinfo knows
            # them) and the database refused them, so a valid zone produced an
            # IntegrityError and a 500.
            #
            # So the two layers answer different questions, each the one it
            # can actually answer — and the boundary sits where the data
            # allows rather than where it felt tidy. **No IANA zone begins
            # with + or -**, so a leading sign is unambiguously an offset
            # literal and the column refuses it. A second clause rejecting
            # "UTC or GMT followed by a sign" looked right and was not: GMT+0
            # and GMT-0 are real zones, which a sweep over every zone caught
            # within a minute of being written.
            #
            # "UTC+5" therefore reaches the column, and the serializer stops
            # it — zoneinfo knows it is not a place. The constraint's job is
            # to hold against a data migration or a shell session writing the
            # canonical offset shape, and that it does.
            models.CheckConstraint(
                check=~Q(timezone__regex=r"^[+-]"),
                name="meeting_timezone_is_not_an_offset",
            ),
            # One live meeting per session. A rescheduled meeting leaves its
            # cancelled predecessor behind, so history survives without a
            # one-to-one that would have to be deleted to reschedule.
            models.UniqueConstraint(
                fields=["session"],
                condition=Q(status="SCHEDULED"),
                name="one_scheduled_meeting_per_session",
            ),
            # FR-CAL-03's verification, in the database rather than in the
            # sync loop: "a round-trip creates no duplicate on either side
            # when sync runs twice, keyed on the provider event ID".
            #
            # Written as a constraint because idempotence enforced only by a
            # get_or_create is idempotence until two cycles overlap — a slow
            # cycle and a manual refresh are enough — and the duplicate it
            # produces is a second copy of a real meeting on somebody's
            # calendar, which is exactly the failure the requirement names.
            #
            # Partial, because the empty string is the overwhelming majority:
            # every meeting that has never been pushed carries it, and a plain
            # unique would allow exactly one of them.
            models.UniqueConstraint(
                fields=["tenant", "provider_event_id"],
                condition=~Q(provider_event_id=""),
                name="one_meeting_per_provider_event",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "starts_at"])]

    def __str__(self) -> str:
        when = self.starts_at.strftime("%Y-%m-%d %H:%M")
        return f"{self.title or 'Onboarding meeting'} @ {when} UTC"


class ConflictWinner(models.TextChoices):
    APP = "APP", "The in-app copy was kept"
    GOOGLE = "GOOGLE", "The Google copy was kept"


class CalendarSyncConflict(models.Model):
    """A change that lost a two-way reconciliation (D-03 AC-4).

    The criterion is explicit that "the losing change is recorded rather than
    discarded silently". A log line does not satisfy that: logs are sampled,
    rotated and unreadable to the operator whose edit vanished. This is a row,
    so the question "what happened to the time I set on Tuesday" has an answer
    somebody can be shown.

    Deliberately not surfaced through the calendar endpoint. Reading these is
    a support and audit concern rather than something the pane should
    interrupt an operator with, and inventing a notifications surface is not
    this story.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    meeting = models.ForeignKey(
        ScheduledMeeting,
        on_delete=models.CASCADE,
        related_name="sync_conflicts",
    )
    winner = models.CharField(max_length=8, choices=ConflictWinner.choices)

    #: What the losing side said, as it was read. A shape rather than prose so
    #: it can be replayed or diffed; whichever side lost, this is the content
    #: that did not survive.
    discarded = models.JSONField(default=dict)

    #: Which rule applied, in words, so a reader does not have to reconstruct
    #: the policy from the code as it was on the day.
    rule = models.CharField(max_length=255, blank=True, default="")

    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-detected_at"]
        indexes = [models.Index(fields=["tenant", "-detected_at"])]

    def __str__(self) -> str:
        return f"{self.winner} won for meeting {self.meeting_id}"
