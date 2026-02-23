"""
Views for the orchestration app.

AnalysisJobViewSet — CRUD + callback + cancel for analysis jobs.
PipelineManifestViewSet — CRUD for pipeline manifests (admin-only create/update).
"""

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tenants.permissions import (
    IsTenantAdmin,
    IsTenantEditor,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)

from .models import AnalysisJob, PipelineManifest
from .serializers import (
    AnalysisJobCreateSerializer,
    AnalysisJobSerializer,
    CallbackSerializer,
    PipelineManifestListSerializer,
    PipelineManifestSerializer,
)
from .tasks import dispatch_job_task

logger = logging.getLogger(__name__)


class AnalysisJobViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing analysis jobs.

    Endpoints:
        POST   /jobs/              — Create + dispatch a new job
        GET    /jobs/              — List user's jobs (tenant-filtered)
        GET    /jobs/{job_id}/     — Get job details + progress + results
        PATCH  /jobs/{job_id}/callback/ — Callback from orchestrator
        POST   /jobs/{job_id}/cancel/  — Cancel a running job
    """

    serializer_class = AnalysisJobSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "job_id"
    http_method_names = ["get", "post", "patch", "head", "options"]

    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantEditor],
        "cancel": [IsAuthenticated, IsTenantEditor],
        "callback": [],  # Service-to-service auth handled in action
    }

    def get_queryset(self):
        """Filter jobs by tenant with backward compatibility.

        Callback action bypasses tenant filtering — it is a
        service-to-service call authenticated via token, not
        per-tenant middleware.
        """
        qs = AnalysisJob.objects.select_related("manifest", "created_by")
        if self.action == "callback":
            return qs
        tenant = getattr(self.request, "tenant", None)
        if tenant:
            qs = qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
        return qs

    def get_serializer_class(self):
        """Use create serializer for POST."""
        if self.action == "create":
            return AnalysisJobCreateSerializer
        return AnalysisJobSerializer

    def perform_create(self, serializer):
        """Create job and dispatch to orchestrator via Celery."""
        tenant = getattr(self.request, "tenant", None)
        job = serializer.save(
            tenant=tenant,
            created_by=self.request.user,
            status=AnalysisJob.Status.QUEUED,
        )
        # Dispatch asynchronously via Celery
        dispatch_job_task.delay(job.id)
        logger.info("Job %s created and queued for dispatch", job.job_id)

    def create(self, request, *args, **kwargs):
        """Override to return full job serializer after creation."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Return full serializer with job_id, status, etc.
        output_serializer = AnalysisJobSerializer(serializer.instance)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="callback")
    def callback(self, request, job_id=None):
        """
        Callback endpoint for pipeline-orchestrator-svc.

        Authenticates via X-Callback-Token header (service-to-service).
        Accepts progress updates, final results, and failure reports.
        Handles resolved_manifest_id for intent routing resolution.
        """
        # Verify callback token
        token = request.META.get("HTTP_X_CALLBACK_TOKEN", "")
        expected_token = getattr(settings, "ORCHESTRATOR_CALLBACK_TOKEN", "")
        if not expected_token or token != expected_token:
            logger.warning("Invalid callback token for job %s", job_id)
            return Response(
                {"error": "Invalid callback token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            # Lock the row to prevent concurrent callback updates
            try:
                job = AnalysisJob.objects.select_for_update().get(job_id=job_id)
            except AnalysisJob.DoesNotExist:
                return Response(
                    {"error": "Job not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            update_fields = ["updated_at"]

            # Update progress
            if "progress" in data:
                job.progress = data["progress"]
                update_fields.append("progress")

            # Update status
            if "status" in data:
                new_status = data["status"]
                job.status = new_status
                update_fields.append("status")

                if new_status == AnalysisJob.Status.COMPLETED:
                    job.completed_at = timezone.now()
                    update_fields.append("completed_at")
                elif new_status == AnalysisJob.Status.FAILED:
                    job.completed_at = timezone.now()
                    update_fields.append("completed_at")

            # Update result_data
            if "result_data" in data:
                job.result_data = data["result_data"]
                update_fields.append("result_data")

            # Update error_message
            if "error_message" in data:
                job.error_message = data["error_message"]
                update_fields.append("error_message")

            # Handle resolved_manifest_id (intent routing resolution)
            if "resolved_manifest_id" in data and job.manifest is None:
                try:
                    resolved = PipelineManifest.objects.get(
                        pipeline_id=data["resolved_manifest_id"],
                        is_active=True,
                    )
                    job.manifest = resolved
                    update_fields.append("manifest")
                    logger.info(
                        "Job %s: manifest resolved to %s via intent routing",
                        job.job_id,
                        data["resolved_manifest_id"],
                    )
                except PipelineManifest.DoesNotExist:
                    logger.warning(
                        "Job %s: resolved_manifest_id '%s' not found",
                        job.job_id,
                        data["resolved_manifest_id"],
                    )

            job.save(update_fields=update_fields)

        # Cache job status in Redis for fast polling
        try:
            cache_data = {
                "status": job.status,
                "progress": job.progress,
            }
            if job.status == AnalysisJob.Status.COMPLETED:
                cache_data["result_data"] = job.result_data
                cache_data["manifest_name"] = (
                    job.manifest.name if job.manifest else None
                )
            elif job.status == AnalysisJob.Status.FAILED:
                cache_data["error_message"] = job.error_message
            cache.set(f"job:status:{job.job_id}", cache_data, timeout=3600)
        except Exception:
            pass  # Cache failures should not break the callback

        logger.info("Job %s callback processed: %s", job.job_id, data)

        return Response({"status": "accepted"})

    @action(detail=True, methods=["get"], url_path="quick-status")
    def quick_status(self, request, job_id=None):
        """Fast status check from Redis cache, falls back to DB.

        Returns a lightweight response optimized for polling.
        """
        cached = cache.get(f"job:status:{job_id}")
        if cached:
            return Response(cached)

        # Fall back to DB
        job = self.get_object()
        data = {
            "status": job.status,
            "progress": job.progress,
        }
        if job.status == AnalysisJob.Status.COMPLETED:
            data["result_data"] = job.result_data
            data["manifest_name"] = job.manifest.name if job.manifest else None
        elif job.status == AnalysisJob.Status.FAILED:
            data["error_message"] = job.error_message

        # Populate cache for subsequent polls
        try:
            cache.set(f"job:status:{job_id}", data, timeout=3600)
        except Exception:
            pass

        return Response(data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, job_id=None):
        """Cancel a queued or running job."""
        job = self.get_object()

        if job.status not in (
            AnalysisJob.Status.QUEUED,
            AnalysisJob.Status.RUNNING,
        ):
            return Response(
                {
                    "error": (
                        f"Job cannot be cancelled " f"(current status: {job.status})"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Notify orchestrator if job is running
        if job.status == AnalysisJob.Status.RUNNING:
            from .services import OrchestratorDispatcher

            dispatcher = OrchestratorDispatcher()
            dispatcher.cancel(job)

        job.status = AnalysisJob.Status.FAILED
        job.error_message = "Cancelled by user"
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )
        logger.info("Job %s cancelled by user %s", job.job_id, request.user)

        return Response(
            AnalysisJobSerializer(job).data,
            status=status.HTTP_200_OK,
        )


class PipelineManifestViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing pipeline manifests.

    Endpoints:
        GET    /manifests/         — List active manifests
        GET    /manifests/{id}/    — Get manifest details
        POST   /manifests/        — Create manifest (admin only)
        PUT    /manifests/{id}/    — Update manifest (admin only)
        DELETE /manifests/{id}/    — Soft-delete manifest (admin only)
    """

    serializer_class = PipelineManifestSerializer
    permission_classes = [IsAuthenticated]

    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantAdmin],
        "update": [IsAuthenticated, IsTenantAdmin],
        "partial_update": [IsAuthenticated, IsTenantAdmin],
        "destroy": [IsAuthenticated, IsTenantAdmin],
    }

    def get_queryset(self):
        """Filter manifests by tenant with backward compatibility."""
        tenant = getattr(self.request, "tenant", None)
        qs = PipelineManifest.objects.filter(is_active=True)
        if tenant:
            qs = qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
        return qs

    def get_serializer_class(self):
        """Use lightweight serializer for list views."""
        if self.action == "list":
            return PipelineManifestListSerializer
        return PipelineManifestSerializer

    def perform_create(self, serializer):
        """Attach tenant and creator on create."""
        tenant = getattr(self.request, "tenant", None)
        serializer.save(
            tenant=tenant,
            created_by=self.request.user,
        )

    def perform_destroy(self, instance):
        """Soft-delete: deactivate instead of hard-deleting."""
        instance.is_active = False
        instance.save(update_fields=["is_active"])
