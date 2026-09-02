"""GDPR erasure and retention API endpoints.

POST  /api/v1/onboarding/erasure/      — queue an erasure cascade (M-02)
GET   /api/v1/onboarding/erasure/logs/  — list erasure audit logs (M-02)
GET   /api/v1/onboarding/retention/     — current retention config (M-03)
PATCH /api/v1/onboarding/retention/     — update retention window (M-03)
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.permissions import IsTenantAdmin

from apps.onboarding.erasure.models import ErasureLog, RetentionConfig
from apps.onboarding.erasure.tasks import execute_erasure_cascade


class ErasureRequestSerializer(serializers.Serializer):
    subject_name = serializers.CharField(max_length=255)
    reason = serializers.CharField(max_length=255, required=False, default="")


class ErasureLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErasureLog
        fields = [
            "id",
            "tenant_id",
            "subject_name",
            "requested_by_id",
            "reason",
            "completion_report",
            "requested_at",
            "completed_at",
        ]
        read_only_fields = fields


class ErasureRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def post(self, request):
        serializer = ErasureRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return Response(
                {"detail": "Tenant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subject_name = serializer.validated_data["subject_name"]
        reason = serializer.validated_data["reason"]

        from django.db.models import Q

        from apps.onboarding.models import ConsentRecord

        exists = ConsentRecord.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            subject_name=subject_name,
        ).exists()
        if not exists:
            return Response(
                {"detail": "No consent records found for this subject."},
                status=status.HTTP_404_NOT_FOUND,
            )

        log_entry = ErasureLog.objects.create(
            tenant=tenant,
            subject_name=subject_name,
            requested_by=request.user,
            reason=reason,
        )

        execute_erasure_cascade.delay(
            tenant_id=str(tenant.pk),
            subject_name=subject_name,
            requested_by_user_id=str(request.user.pk),
            reason=reason,
            erasure_log_id=log_entry.pk,
        )

        return Response(
            ErasureLogSerializer(log_entry).data,
            status=status.HTTP_202_ACCEPTED,
        )


class ErasureLogListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return Response(
                {"detail": "Tenant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logs = ErasureLog.objects.filter(tenant=tenant).order_by("-created_at")[:50]
        serializer = ErasureLogSerializer(logs, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# M-03 · Retention configuration
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_DAYS = 365


class RetentionConfigUpdateSerializer(serializers.Serializer):
    retention_days = serializers.IntegerField(min_value=1, max_value=3650)


def _next_enforcement_run():
    """Next 03:00 UTC from now."""
    now = timezone.now()
    next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def _compute_impact(tenant, new_days, old_days):
    from apps.onboarding.models import ConsentRecord

    new_cutoff = timezone.now() - timedelta(days=new_days)
    old_cutoff = timezone.now() - timedelta(days=old_days)

    affected = (
        ConsentRecord.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            revoked_at__isnull=True,
        )
        .values("subject_name")
        .annotate(latest=Max("session__created_at"))
        .filter(latest__lt=new_cutoff, latest__gte=old_cutoff)
    )

    subject_names = [a["subject_name"] for a in affected]
    subject_count = len(subject_names)

    session_count = 0
    if subject_names:
        session_count = (
            ConsentRecord.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                subject_name__in=subject_names,
            )
            .values_list("session_id", flat=True)
            .distinct()
            .count()
        )

    return {
        "subjects": subject_count,
        "sessions": session_count,
        "enforced_at": _next_enforcement_run().isoformat(),
    }


class RetentionConfigView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return Response(
                {"detail": "Tenant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config = RetentionConfig.objects.filter(tenant=tenant).first()
        return Response(
            {
                "retention_days": (
                    config.retention_days if config else DEFAULT_RETENTION_DAYS
                ),
                "is_default": config is None,
                "next_enforcement_run": _next_enforcement_run().isoformat(),
            }
        )

    def patch(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return Response(
                {"detail": "Tenant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RetentionConfigUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_days = serializer.validated_data["retention_days"]

        config = RetentionConfig.objects.filter(tenant=tenant).first()
        old_days = config.retention_days if config else DEFAULT_RETENTION_DAYS

        impact = None
        if new_days < old_days:
            impact = _compute_impact(tenant, new_days, old_days)

        if config:
            config.retention_days = new_days
            config.save(update_fields=["retention_days", "updated_at"])
        else:
            config = RetentionConfig.objects.create(
                tenant=tenant, retention_days=new_days
            )

        data = {
            "retention_days": config.retention_days,
            "previous_days": old_days,
            "is_default": False,
            "next_enforcement_run": _next_enforcement_run().isoformat(),
        }
        if impact is not None:
            data["impact"] = impact

        return Response(data)
