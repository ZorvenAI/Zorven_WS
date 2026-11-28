"""GDPR erasure and retention API endpoints.

POST  /api/v1/onboarding/erasure/      — queue an erasure cascade (M-02)
GET   /api/v1/onboarding/erasure/logs/  — list erasure audit logs (M-02)
GET   /api/v1/onboarding/retention/     — current retention config (M-03)
PATCH /api/v1/onboarding/retention/     — update retention window (M-03)
GET   /api/v1/onboarding/erasure/review/              — held requests
POST  /api/v1/onboarding/erasure/review/<id>/keep/    — keep under legal hold
POST  /api/v1/onboarding/erasure/review/<id>/erase/   — erase held sessions anyway
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.permissions import IsTenantAdmin

from apps.onboarding.erasure.models import (
    LEGAL_HOLD_YEARS_DEFAULT,
    LEGAL_HOLD_YEARS_MAX,
    LEGAL_HOLD_YEARS_MIN,
    RETENTION_DAYS_DEFAULT,
    RETENTION_DAYS_MAX,
    RETENTION_DAYS_MIN,
    ErasureLog,
    RetentionConfig,
    ReviewStatus,
)
from apps.onboarding.erasure import review
from apps.onboarding.erasure.review import (
    ReviewError,
    days_waiting,
    default_hold_until,
    held_session_ids,
    is_overdue,
)
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


class RetentionConfigUpdateSerializer(serializers.Serializer):
    # Each optional on its own, so the retention window and the legal hold
    # period can be saved separately; at least one is required.
    retention_days = serializers.IntegerField(
        min_value=RETENTION_DAYS_MIN, max_value=RETENTION_DAYS_MAX, required=False
    )
    legal_hold_years = serializers.IntegerField(
        min_value=LEGAL_HOLD_YEARS_MIN, max_value=LEGAL_HOLD_YEARS_MAX, required=False
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Send retention_days, legal_hold_years, or both."
            )
        return attrs


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
                    config.retention_days if config else RETENTION_DAYS_DEFAULT
                ),
                "legal_hold_years": (
                    config.legal_hold_years if config else LEGAL_HOLD_YEARS_DEFAULT
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
        config = RetentionConfig.objects.filter(tenant=tenant).first()
        old_days = config.retention_days if config else RETENTION_DAYS_DEFAULT
        old_years = config.legal_hold_years if config else LEGAL_HOLD_YEARS_DEFAULT
        new_days = serializer.validated_data.get("retention_days", old_days)
        new_years = serializer.validated_data.get("legal_hold_years", old_years)

        preview = request.query_params.get("preview") == "true"

        impact = None
        if new_days < old_days:
            impact = _compute_impact(tenant, new_days, old_days)

        if preview:
            data = {
                "retention_days": new_days,
                "legal_hold_years": new_years,
                "previous_days": old_days,
                "is_default": config is None,
                "next_enforcement_run": _next_enforcement_run().isoformat(),
            }
            if impact is not None:
                data["impact"] = impact
            return Response(data)

        if config:
            config.retention_days = new_days
            config.legal_hold_years = new_years
            config.save(
                update_fields=["retention_days", "legal_hold_years", "updated_at"]
            )
        else:
            config = RetentionConfig.objects.create(
                tenant=tenant, retention_days=new_days, legal_hold_years=new_years
            )

        data = {
            "retention_days": config.retention_days,
            "legal_hold_years": config.legal_hold_years,
            "previous_days": old_days,
            "is_default": False,
            "next_enforcement_run": _next_enforcement_run().isoformat(),
        }
        if impact is not None:
            data["impact"] = impact

        return Response(data)


# ---------------------------------------------------------------------------
# Review queue · erasure requests held for signed meeting records
# ---------------------------------------------------------------------------


def _held_detail(log: ErasureLog) -> list[dict]:
    """The held sessions with their company and records, as they stand now."""
    from apps.onboarding.models import OnboardingSession
    from apps.onboarding.records.models import FROZEN_RECORD_STATUSES, MeetingRecord

    ids = held_session_ids(log)
    sessions = {
        str(s.pk): s
        for s in OnboardingSession.objects.filter(pk__in=ids).select_related("company")
    }
    records: dict[str, list[dict]] = {}
    for r in MeetingRecord.objects.filter(
        session_id__in=ids, status__in=FROZEN_RECORD_STATUSES
    ).order_by("record_number"):
        records.setdefault(str(r.session_id), []).append(
            {"record_number": r.record_number, "status": r.status}
        )
    return [
        {
            "session_id": sid,
            "company_name": (
                getattr(getattr(sessions.get(sid), "company", None), "name", "") or ""
            ),
            "records": records.get(sid, []),
        }
        for sid in ids
    ]


def _review_payload(log: ErasureLog) -> dict:
    report = log.completion_report or {}
    return {
        "id": log.pk,
        "subject_name": log.subject_name,
        "reason": log.reason,
        "requested_at": log.requested_at.isoformat(),
        "requested_by": getattr(log.requested_by, "username", None),
        "days_waiting": days_waiting(log),
        "overdue": log.review_status == ReviewStatus.PENDING and is_overdue(log),
        "held": _held_detail(log),
        "review_status": log.review_status,
        "reviewed_by": getattr(log.reviewed_by, "username", None),
        "reviewed_at": log.reviewed_at.isoformat() if log.reviewed_at else None,
        "review_reason": log.review_reason,
        "hold_until": log.hold_until.isoformat() if log.hold_until else None,
        "erase_in_progress": (
            log.review_status == ReviewStatus.PENDING and log.reviewed_at is not None
        ),
        "last_error": report.get("review_erase_error", ""),
        "erased_signed_records": (
            report.get("review_erase", {}).get("erased_signed_records", [])
        ),
        "default_hold_until": default_hold_until(log.tenant).isoformat(),
    }


def _tenant_log(request, pk) -> ErasureLog | None:
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return None
    return (
        ErasureLog.objects.filter(tenant=tenant, pk=pk)
        .exclude(review_status=ReviewStatus.NONE)
        .select_related("tenant", "requested_by", "reviewed_by")
        .first()
    )


def _review_error(exc: ReviewError) -> Response:
    return Response({"error": exc.code, "detail": exc.detail}, status=exc.status)


class KeepSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=True)
    hold_until = serializers.DateField(required=False, allow_null=True)


class EraseAnywaySerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=True)
    confirm_subject = serializers.CharField(allow_blank=True)


class ErasureReviewListView(APIView):
    """``GET erasure/review/`` -- held requests, oldest first.

    ``?status=KEPT`` or ``?status=ERASED`` lists decided requests instead.
    """

    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return Response(
                {"detail": "Tenant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        wanted = request.query_params.get("status") or ReviewStatus.PENDING
        if wanted not in (ReviewStatus.PENDING, ReviewStatus.KEPT, ReviewStatus.ERASED):
            return Response(
                {"detail": "status must be PENDING, KEPT or ERASED."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = "requested_at" if wanted == ReviewStatus.PENDING else "-reviewed_at"
        logs = (
            ErasureLog.objects.filter(tenant=tenant, review_status=wanted)
            .select_related("tenant", "requested_by", "reviewed_by")
            .order_by(order)[:200]
        )
        return Response([_review_payload(log) for log in logs])


class ErasureReviewKeepView(APIView):
    """``POST erasure/review/<pk>/keep/`` -- keep the held sessions."""

    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def post(self, request, pk):
        log = _tenant_log(request, pk)
        if log is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        body = KeepSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            log = review.keep(
                log,
                user=request.user,
                reason=body.validated_data["reason"],
                hold_until=body.validated_data.get("hold_until"),
            )
        except ReviewError as exc:
            return _review_error(exc)
        return Response(_review_payload(_tenant_log(request, log.pk)))


class ErasureReviewEraseView(APIView):
    """``POST erasure/review/<pk>/erase/`` -- erase the held sessions anyway."""

    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def post(self, request, pk):
        log = _tenant_log(request, pk)
        if log is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        body = EraseAnywaySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            log = review.erase_anyway(
                log,
                user=request.user,
                reason=body.validated_data["reason"],
                confirm_subject=body.validated_data["confirm_subject"],
            )
        except ReviewError as exc:
            return _review_error(exc)
        return Response(
            _review_payload(_tenant_log(request, log.pk)),
            status=status.HTTP_202_ACCEPTED,
        )
