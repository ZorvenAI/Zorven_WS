"""M-02 · GDPR erasure API endpoint.

POST /api/v1/onboarding/erasure/ — queues an erasure cascade for a
subject within the request tenant. Returns 202 immediately.
"""

from __future__ import annotations

from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.permissions import IsTenantAdmin

from apps.onboarding.erasure.models import ErasureLog
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
