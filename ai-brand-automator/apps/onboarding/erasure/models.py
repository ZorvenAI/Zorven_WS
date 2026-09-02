"""M-02 · ErasureLog model — GDPR erasure audit trail.

Every cascade execution records its completion report here so that the
tenant admin and any future compliance audit can show what was erased,
when, and whether it succeeded.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


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
