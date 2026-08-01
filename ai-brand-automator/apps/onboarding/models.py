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
from django.db.models import Q

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
        if tenant is None:
            return self.get_queryset().filter(tenant__isnull=True)
        return self.get_queryset().filter(Q(tenant=tenant) | Q(tenant__isnull=True))


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
        related_name="questionnaires",
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
    is_template = models.BooleanField(
        default=False,
        help_text="Reusable for another company in the same tenant (D-05)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        ordering = ["-created_at"]
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
