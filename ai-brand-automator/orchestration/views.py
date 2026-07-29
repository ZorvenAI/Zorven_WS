"""
Views for the orchestration app.

AnalysisJobViewSet — CRUD + callback + cancel for analysis jobs.
PipelineManifestViewSet — CRUD for pipeline manifests (admin-only create/update).
"""

import logging

from decouple import config as decouple_config
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from tenants.permissions import (
    IsTenantAdmin,
    IsTenantEditor,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)

from .models import AnalysisJob, PipelineManifest, TrendNotification
from .result_handler import handle_pipeline_result
from .serializers import (
    AnalysisJobCreateSerializer,
    AnalysisJobSerializer,
    CallbackSerializer,
    PipelineManifestListSerializer,
    PipelineManifestSerializer,
    TrendNotificationCreateSerializer,
    TrendNotificationSerializer,
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
        "approve": [IsAuthenticated, IsTenantEditor],
        "callback": [],  # Service-to-service auth handled in action
    }

    def get_queryset(self):
        """Filter jobs by tenant with backward compatibility.

        Callback action bypasses tenant filtering — it is a
        service-to-service call authenticated via token, not
        per-tenant middleware.

        Supports ``?status=`` query-param filtering (e.g. ``?status=completed``).
        """
        qs = AnalysisJob.objects.select_related("manifest", "created_by")
        if self.action == "callback":
            return qs
        tenant = getattr(self.request, "tenant", None)
        if tenant:
            qs = qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))

        # Optional status filter
        status = self.request.query_params.get("status")
        if status and status in AnalysisJob.Status.values:
            qs = qs.filter(status=status)

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
        """Fast status check optimized for polling.

        For **terminal** jobs (completed / failed) the response is served
        from Redis cache (1-hour TTL) since it won't change.

        For **in-flight** jobs (queued / running) the response is ALWAYS
        read from the database.  This eliminates a class of stale-cache
        bugs where the Redis entry written by a quick-status DB-fallback
        (with empty progress) races against the callback's cache write,
        leaving the frontend stuck on an empty agent list.  The DB read
        is a single indexed lookup and takes <10 ms — acceptable at
        the 3-second polling interval.
        """
        # ── Try Redis cache for terminal jobs only ──
        cached = cache.get(f"job:status:{job_id}")
        if cached and cached.get("status") in (
            "completed",
            "failed",
            "awaiting_approval",
        ):
            cached.setdefault("current_node", None)
            cached.setdefault("progress_percent", 0)
            cached.setdefault("last_thought", None)
            resp = Response(cached)
            resp["Cache-Control"] = "no-store"
            return resp

        # ── Read from DB (in-flight or cache miss) ──
        job = self.get_object()
        progress = job.progress or {}
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
        # Include result_data whenever available (partial results during
        # execution, full results when completed)
        if job.result_data:
            data["result_data"] = job.result_data
        if job.status == AnalysisJob.Status.COMPLETED:
            data["manifest_name"] = job.manifest.name if job.manifest else None
            data["progress_percent"] = 100
        elif job.status == AnalysisJob.Status.FAILED:
            data["error_message"] = job.error_message
        elif job.status == AnalysisJob.Status.AWAITING_APPROVAL:
            data["manifest_name"] = job.manifest.name if job.manifest else None
            data["progress_percent"] = 100

        # Cache terminal states for 1 hour; skip caching in-flight
        # jobs — the DB is the source of truth during execution.
        is_terminal = job.status in (
            AnalysisJob.Status.COMPLETED,
            AnalysisJob.Status.FAILED,
            AnalysisJob.Status.AWAITING_APPROVAL,
        )
        if is_terminal:
            try:
                cache.set(f"job:status:{job_id}", data, timeout=3600)
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
            if isinstance(v, dict)
            and v.get("status") in ("done", "failed", "awaiting_approval")
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

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, job_id=None):
        """Proxy human approval decision to the ad-publishing agent.

        The frontend cannot call the ad-publishing service directly
        (service-to-service auth). This endpoint forwards the approval
        decision and returns the result.
        """
        from brand_automator.validators import sanitize_text_input

        job = self.get_object()

        if job.status != AnalysisJob.Status.AWAITING_APPROVAL:
            return Response(
                {"error": f"Job is not awaiting approval (status: {job.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate approval_request_id
        approval_request_id = str(
            request.data.get("approval_request_id", "") or ""
        ).strip()
        if not approval_request_id:
            return Response(
                {"error": "approval_request_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        decision = request.data.get("decision", "")
        if decision not in ("approve_all", "approve_selected", "reject"):
            return Response(
                {"error": "decision must be approve_all, approve_selected, or reject"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate approved_ad_sets for approve_selected
        approved_ad_sets = request.data.get("approved_ad_sets")
        if decision == "approve_selected":
            if not isinstance(approved_ad_sets, list) or not approved_ad_sets:
                return Response(
                    {
                        "error": (
                            "approved_ad_sets must be a non-empty list when "
                            "decision is approve_selected"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            approved_ad_sets = None

        # Sanitize feedback and derive user_role server-side
        feedback = sanitize_text_input(
            request.data.get("feedback", ""), max_length=2000
        )
        tenant = getattr(request, "tenant", None)
        tenant_id = str(tenant.id) if tenant else ""
        user_role = "VIEWER"
        if tenant and request.user:
            role = tenant.get_user_role(request.user)
            user_role = role.upper() if role else "VIEWER"

        payload = {
            "approval_request_id": approval_request_id,
            "decision": decision,
            "approved_ad_sets": approved_ad_sets,
            "feedback": feedback,
            "production_confirmed": bool(
                request.data.get("production_confirmed", False)
            ),
            "approved_by": request.user.email if request.user else "",
            "user_role": user_role,
        }

        # Forward to ad-publishing agent
        adpub_url = decouple_config(
            "AD_PUBLISHING_AGENT_URL",
            default="http://localhost:8043",
        )
        adpub_token = decouple_config(
            "AD_PUBLISHING_SERVICE_TOKEN",
            default="dev-service-token",
        )

        import requests as http_requests

        try:
            resp = http_requests.post(
                f"{adpub_url}/v1/approve",
                json=payload,
                headers={
                    "X-Service-Token": adpub_token,
                    "X-Tenant-ID": tenant_id,
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
        except http_requests.RequestException:
            logger.exception(
                "Failed to reach ad-publishing service for job %s",
                job_id,
            )
            return Response(
                {"error": "Failed to reach ad-publishing service."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not resp.ok:
            logger.error(
                "Ad-publishing service returned error for job %s: " "status=%s body=%r",
                job_id,
                resp.status_code,
                resp.text[:500],
            )
            response_status = (
                resp.status_code
                if 400 <= resp.status_code < 500
                else status.HTTP_502_BAD_GATEWAY
            )
            return Response(
                {"error": "Ad-publishing service returned an error."},
                status=response_status,
            )

        try:
            result = resp.json()
        except ValueError:
            logger.error(
                "Ad-publishing service returned non-JSON response "
                "for job %s: status=%s body=%r",
                job_id,
                resp.status_code,
                resp.text[:500],
            )
            return Response(
                {"error": "Invalid response from ad-publishing service."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Persist outcome on the job so it doesn't stay awaiting_approval
        from orchestration.result_handler import (
            _update_redis_cache,
            _release_session_lock,
            _save_final_chat_message,
            _update_workflow_snapshot,
            _broadcast_to_workspace,
        )

        new_status = None

        if decision == "reject":
            new_status = AnalysisJob.Status.FAILED
            job.status = new_status
            job.error_message = "Rejected by user"
            job.completed_at = timezone.now()
            job.save(
                update_fields=[
                    "status",
                    "error_message",
                    "completed_at",
                    "updated_at",
                ]
            )
        elif decision in ("approve_all", "approve_selected"):
            publish_status = result.get("status", "")
            if publish_status in ("published", "completed", "partial"):
                new_status = AnalysisJob.Status.COMPLETED
                job.status = new_status
                job.completed_at = timezone.now()
                # Merge publish result into node_results.ad_publishing
                # so the frontend finds it in the expected location.
                existing = job.result_data or {}
                node_results = existing.get("node_results", {})
                ad_pub_node = node_results.get("ad_publishing", {})
                if isinstance(ad_pub_node, dict):
                    ad_pub_node["publish_result"] = result
                    ad_pub_node["status"] = "completed"
                else:
                    ad_pub_node = {"publish_result": result, "status": "completed"}
                node_results["ad_publishing"] = ad_pub_node
                existing["node_results"] = node_results
                existing["publish_result"] = result
                job.result_data = existing
                # Mark ALL remaining pipeline nodes as done so the
                # pipeline graph shows complete (e.g. manager node).
                progress = job.progress or {}
                completed_at = timezone.now().isoformat()
                for node_id, node_info in progress.items():
                    if isinstance(node_info, dict) and node_info.get("status") in (
                        "pending",
                        "awaiting_approval",
                    ):
                        node_info["status"] = "done"
                        node_info.setdefault("completed_at", completed_at)
                job.progress = progress
                job.save(
                    update_fields=[
                        "status",
                        "completed_at",
                        "result_data",
                        "progress",
                        "updated_at",
                    ]
                )
            elif publish_status in ("failed", "error"):
                new_status = AnalysisJob.Status.FAILED
                job.status = new_status
                job.error_message = result.get("error", "Publishing failed")
                job.completed_at = timezone.now()
                job.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "completed_at",
                        "updated_at",
                    ]
                )

        # Update Redis cache and run post-completion handlers
        # (same as handle_pipeline_result does for normal completions)
        _update_redis_cache(job)
        _broadcast_to_workspace(job, new_status)
        if new_status in (
            AnalysisJob.Status.COMPLETED,
            AnalysisJob.Status.FAILED,
        ):
            _release_session_lock(job)
            if new_status == AnalysisJob.Status.COMPLETED:
                _save_final_chat_message(job)
                _update_workflow_snapshot(job)
                try:
                    from analytics.tasks import extract_metrics_task

                    extract_metrics_task.delay(job.id)
                except Exception:
                    logger.exception(
                        "Failed to dispatch analytics for job %s",
                        job.job_id,
                    )

        logger.info(
            "Job %s approval proxied: decision=%s, result_status=%s",
            job_id,
            decision,
            result.get("status", "unknown"),
        )
        return Response(result, status=status.HTTP_200_OK)


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


@api_view(["GET"])
@permission_classes([AllowAny])
def callback_debug(request):
    """Diagnostic endpoint for verifying callback configuration.

    Requires ``X-Service-Token`` header for authentication so that
    internal configuration is not exposed publicly.
    """
    token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    expected = getattr(settings, "ORCHESTRATOR_SERVICE_TOKEN", "")
    if not expected or token != expected:
        return Response(
            {"error": "Invalid or missing X-Service-Token"},
            status=status.HTTP_403_FORBIDDEN,
        )

    cb_token = getattr(settings, "ORCHESTRATOR_CALLBACK_TOKEN", "")
    return Response(
        {
            "allowed_hosts": settings.ALLOWED_HOSTS,
            "callback_base_url": decouple_config(
                "CALLBACK_BASE_URL", default="(not set)"
            ),
            "backend_url": decouple_config("BACKEND_URL", default="(not set)"),
            "orchestrator_url": getattr(settings, "ORCHESTRATOR_URL", "(not set)"),
            "callback_token_configured": bool(cb_token),
            "service_name": decouple_config("K_SERVICE", default="(not set)"),
            "revision": decouple_config("K_REVISION", default="(not set)"),
            "host_header": request.META.get("HTTP_HOST", "(none)"),
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def push_notification(request):
    """Receive push notifications from TCIA service.

    Authenticated via X-Service-Token header (same as orchestrator callbacks).
    Creates a TrendNotification record for the specified tenant.
    """
    token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    expected = getattr(settings, "ORCHESTRATOR_SERVICE_TOKEN", "")
    if not expected or token != expected:
        return Response(
            {"error": "Invalid or missing X-Service-Token"},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = TrendNotificationCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # Resolve tenant
    tenant = None
    tenant_id = data.get("tenant_id")
    if tenant_id:
        from tenants.models import Tenant

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except (Tenant.DoesNotExist, ValueError):
            logger.warning("push_notification: tenant %s not found", tenant_id)

    notification = TrendNotification.objects.create(
        tenant=tenant,
        notification_type=data["notification_type"],
        title=data["title"],
        body=data["body"],
        metadata=data.get("metadata", {}),
    )

    return Response(
        TrendNotificationSerializer(notification).data,
        status=status.HTTP_201_CREATED,
    )
