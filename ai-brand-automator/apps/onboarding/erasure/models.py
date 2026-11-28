"""GDPR erasure models — audit trail and retention configuration.

ErasureLog (M-02): records each cascade execution.
RetentionConfig (M-03): per-tenant retention window, enforced by a daily
Celery Beat job that feeds M-02's cascade.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

RETENTION_DAYS_MIN = 1
RETENTION_DAYS_MAX = 3650
RETENTION_DAYS_DEFAULT = 365

#: How long a kept erasure request holds its signed records (decision D7).
LEGAL_HOLD_YEARS_MIN = 1
LEGAL_HOLD_YEARS_MAX = 25
LEGAL_HOLD_YEARS_DEFAULT = 7


class ReviewStatus(models.TextChoices):
    """Where a held erasure request stands. Empty when nothing was held."""

    NONE = "", "Not held"
    PENDING = "PENDING", "Awaiting review"
    KEPT = "KEPT", "Kept under legal hold"
    ERASED = "ERASED", "Erased on review"


class ErasureLog(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
    )
    subject_name = models.CharField(max_length=255)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erasure_requests",
    )
    reason = models.CharField(max_length=255, default="")
    completion_report = models.JSONField(default=dict, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # ── Review of sessions held for signed meeting records ───────────
    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.NONE,
        blank=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erasure_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(blank=True, default="")
    hold_until = models.DateField(
        null=True,
        blank=True,
        help_text="A kept request returns to the review queue on this date.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "review_status"])]

    def __str__(self):
        return f"Erasure({self.subject_name}, tenant={self.tenant_id})"


class RetentionConfig(models.Model):
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="retention_config",
    )
    retention_days = models.PositiveIntegerField(
        default=RETENTION_DAYS_DEFAULT,
        validators=[
            MinValueValidator(RETENTION_DAYS_MIN),
            MaxValueValidator(RETENTION_DAYS_MAX),
        ],
    )
    legal_hold_years = models.PositiveSmallIntegerField(
        default=LEGAL_HOLD_YEARS_DEFAULT,
        validators=[
            MinValueValidator(LEGAL_HOLD_YEARS_MIN),
            MaxValueValidator(LEGAL_HOLD_YEARS_MAX),
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(
                    retention_days__gte=RETENTION_DAYS_MIN,
                    retention_days__lte=RETENTION_DAYS_MAX,
                ),
                name="retention_days_range",
            ),
            models.CheckConstraint(
                check=models.Q(
                    legal_hold_years__gte=LEGAL_HOLD_YEARS_MIN,
                    legal_hold_years__lte=LEGAL_HOLD_YEARS_MAX,
                ),
                name="legal_hold_years_range",
            ),
        ]

    def __str__(self):
        return (
            f"RetentionConfig(tenant={self.tenant_id}, " f"days={self.retention_days})"
        )
