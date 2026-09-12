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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

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
        ]

    def __str__(self):
        return (
            f"RetentionConfig(tenant={self.tenant_id}, " f"days={self.retention_days})"
        )
