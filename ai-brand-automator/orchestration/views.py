"""
Views for the orchestration app.

AnalysisJobViewSet — CRUD + callback + cancel for analysis jobs.
PipelineManifestViewSet — CRUD for pipeline manifests (admin-only create/update).
"""

import logging

from django.conf import settings
from django.core.cache import cache
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
from .result_handler import handle_pipeline_result
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

        progress = data.get("progress")
        progress_nodes = list(progress.keys()) if isinstance(progress, dict) else []
        try:
            host = request.get_host()
        except Exception:
            host = request.META.get("HTTP_HOST", "<unknown>")
        logger.info(
            "Job %s callback received: status=%s, progress_nodes=%s, "
            "has_result_data=%s, host=%s",
            job_id,
            data.get("status"),
            progress_nodes,
            "result_data" in data,
            host,
        )

        found = handle_pipeline_result(
            job_id,
            status=data.get("status"),
            progress=progress,
            result_data=data.get("result_data"),
            error_message=data.get("error_message"),
            resolved_manifest_id=data.get("resolved_manifest_id"),
        )

        if not found:
            logger.warning("Job %s callback: job not found in DB", job_id)
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.info(
            "Job %s callback processed OK: %d node(s) in progress",
            job_id,
            len(progress_nodes),
        )
        return Response({"status": "accepted"})

    @action(detail=True, methods=["get"], url_path="quick-status")
    def quick_status(self, request, job_id=None):
        """Fast status check from Redis cache, falls back to DB.

        Returns a lightweight response optimized for polling.
        Includes trace fields (current_node, progress_percent, last_thought)
        populated by the Kafka TraceConsumer.

        Cache-Control: no-store prevents Railway's edge proxy and the
        browser from caching the response — the frontend polls every 3s
        and must always see fresh progress data.
        """
        cached = cache.get(f"job:status:{job_id}")
        if cached:
            # If the job is in-flight but progress is still empty, it
            # likely means callbacks haven't updated the cache yet (e.g.
            # the DB-fallback path ran before the first callback arrived
            # and created a stale entry).  Fall through to DB in that
            # case so the next callback's cache write is authoritative.
            in_flight = cached.get("status") in ("queued", "running")
            has_progress = bool(cached.get("progress"))
            if not (in_flight and not has_progress):
                # Ensure trace fields are present even if not yet set
                cached.setdefault("current_node", None)
                cached.setdefault("progress_percent", 0)
                cached.setdefault("last_thought", None)
                resp = Response(cached)
                resp["Cache-Control"] = "no-store"
                return resp

        # Fall back to DB
        job = self.get_object()
        progress = job.progress or {}
        # Derive current_node from progress dict (same logic as cache)
        current_node = next(
            (
                nid
                for nid, info in progress.items()
                if isinstance(info, dict) and info.get("status") == "running"
            ),
            None,
        )
        data = {
            "status": job.status,
            "progress": progress,
            "current_node": current_node,
            "progress_percent": self._calc_percent(progress),
            "last_thought": None,
        }
        if job.status == AnalysisJob.Status.COMPLETED:
            data["result_data"] = job.result_data
            data["manifest_name"] = job.manifest.name if job.manifest else None
            data["progress_percent"] = 100
        elif job.status == AnalysisJob.Status.FAILED:
            data["error_message"] = job.error_message

        # Populate cache for subsequent polls.
        # Use a short TTL for in-flight jobs so stale entries expire
        # quickly if callbacks don't update the cache.  Terminal jobs
        # use a longer TTL (1 hour) since they won't change.
        is_terminal = job.status in (
            AnalysisJob.Status.COMPLETED,
            AnalysisJob.Status.FAILED,
        )
        cache_ttl = 3600 if is_terminal else 30
        try:
            cache.set(f"job:status:{job_id}", data, timeout=cache_ttl)
        except Exception:
            pass

        resp = Response(data)
        resp["Cache-Control"] = "no-store"
        return resp

    @staticmethod
    def _calc_percent(progress):
        """Estimate overall progress from per-agent statuses."""
        if not progress:
            return 0
        total = len(progress)
        done = sum(
            1
            for v in progress.values()
            if isinstance(v, dict) and v.get("status") in ("done", "failed")
        )
        return int((done / total) * 100) if total else 0

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
