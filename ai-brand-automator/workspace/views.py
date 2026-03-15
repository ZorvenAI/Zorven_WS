"""
Views for the workspace app.

WorkflowViewSet — CRUD + execute + clone + export/import + snapshots.
agent_catalog — agent catalog with metadata.
link_from_chat — link chat job to workspace workflow.
"""

import logging

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orchestration.models import AnalysisJob
from orchestration.serializers import AnalysisJobSerializer
from tenants.permissions import (
    IsTenantAdmin,
    IsTenantEditor,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)

from .models import UserWorkflow
from .serializers import (
    AgentCatalogSerializer,
    ChatLinkSerializer,
    SnapshotListSerializer,
    WorkflowCloneSerializer,
    WorkflowCreateSerializer,
    WorkflowDetailSerializer,
    WorkflowExecuteSerializer,
    WorkflowImportSerializer,
    WorkflowListSerializer,
    WorkflowUpdateSerializer,
)
from .services import WorkflowService

logger = logging.getLogger(__name__)


class WorkflowViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing user workflows.

    Endpoints:
        GET    /workflows/                         — List workflows
        POST   /workflows/                         — Create workflow
        GET    /workflows/{workflow_id}/            — Get workflow detail
        PUT    /workflows/{workflow_id}/            — Update workflow
        DELETE /workflows/{workflow_id}/            — Soft-delete workflow
        POST   /workflows/{workflow_id}/execute/    — Execute workflow
        POST   /workflows/{workflow_id}/clone/      — Clone workflow
        POST   /workflows/{workflow_id}/export/     — Export workflow
        GET    /workflows/{workflow_id}/snapshots/  — List snapshots
    """

    serializer_class = WorkflowDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "workflow_id"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantEditor],
        "update": [IsAuthenticated, IsTenantEditor],
        "partial_update": [IsAuthenticated, IsTenantEditor],
        "destroy": [IsAuthenticated, IsTenantAdmin],
        "execute": [IsAuthenticated, IsTenantEditor],
        "clone": [IsAuthenticated, IsTenantEditor],
        "export_workflow": [IsAuthenticated, IsTenantViewer],
        "import_workflow": [IsAuthenticated, IsTenantEditor],
        "snapshots": [IsAuthenticated, IsTenantViewer],
        "editing_lock": [IsAuthenticated, IsTenantViewer],
        "templates": [IsAuthenticated, IsTenantViewer],
    }

    def get_queryset(self):
        """Filter workflows by tenant with backward compatibility."""
        qs = UserWorkflow.objects.select_related("manifest", "created_by").filter(
            is_active=True
        )
        tenant = getattr(self.request, "tenant", None)
        if tenant:
            qs = qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return WorkflowListSerializer
        if self.action == "create":
            return WorkflowCreateSerializer
        if self.action in ("update", "partial_update"):
            return WorkflowUpdateSerializer
        return WorkflowDetailSerializer

    def create(self, request, *args, **kwargs):
        """Create a new workflow with manifest."""
        serializer = WorkflowCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = getattr(request, "tenant", None)
        workflow = WorkflowService.create_workflow(
            name=data["name"],
            description=data.get("description", ""),
            manifest_data=data["manifest_data"],
            layout_data=data.get("layout_data", {}),
            tenant=tenant,
            user=request.user,
        )

        output = WorkflowDetailSerializer(workflow)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update workflow manifest and/or metadata."""
        workflow = self.get_object()
        partial = kwargs.pop("partial", False)
        serializer = WorkflowUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        workflow = WorkflowService.update_workflow(workflow, serializer.validated_data)

        output = WorkflowDetailSerializer(workflow)
        return Response(output.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        """Soft-delete: set is_active=False."""
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request, workflow_id=None):
        """Execute a workflow."""
        workflow = self.get_object()
        serializer = WorkflowExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            job = WorkflowService.execute_workflow(
                workflow=workflow,
                input_prompt=data["input_prompt"],
                input_context=data.get("input_context", {}),
                user=request.user,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return Response(
            AnalysisJobSerializer(job).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, workflow_id=None):
        """Clone a workflow."""
        workflow = self.get_object()
        serializer = WorkflowCloneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant = getattr(request, "tenant", None)
        new_workflow = WorkflowService.clone_workflow(
            source_workflow=workflow,
            new_name=serializer.validated_data["name"],
            tenant=tenant,
            user=request.user,
        )

        output = WorkflowDetailSerializer(new_workflow)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="export")
    def export_workflow(self, request, workflow_id=None):
        """Export a workflow as sanitized JSON."""
        workflow = self.get_object()
        data = WorkflowService.export_workflow(workflow)
        return Response(data)

    @action(detail=False, methods=["post"], url_path="import")
    def import_workflow(self, request):
        """Import a workflow from JSON."""
        serializer = WorkflowImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = getattr(request, "tenant", None)
        workflow = WorkflowService.import_workflow(
            name=data["name"],
            description=data.get("description", ""),
            manifest_data=data["manifest_data"],
            layout_data=data.get("layout_data", {}),
            tenant=tenant,
            user=request.user,
        )

        output = WorkflowDetailSerializer(workflow)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="snapshots")
    def snapshots(self, request, workflow_id=None):
        """List snapshots for a workflow (paginated)."""
        workflow = self.get_object()
        snapshots = workflow.snapshots.select_related("job").all()
        page = self.paginate_queryset(snapshots)
        if page is not None:
            serializer = SnapshotListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = SnapshotListSerializer(snapshots, many=True)
        return Response(serializer.data)

    # ── Editing Lock (Phase 2) ──

    @action(detail=True, methods=["get", "post", "delete"], url_path="lock")
    def editing_lock(self, request, workflow_id=None):
        """Manage editing lock: GET=check, POST=acquire, DELETE=release."""
        workflow = self.get_object()
        tenant = getattr(request, "tenant", None)
        tenant_id = tenant.id if tenant else 0
        wid = str(workflow.workflow_id)

        if request.method == "GET":
            info = WorkflowService.get_lock_info(workflow_id=wid, tenant_id=tenant_id)
            if info:
                return Response(
                    {
                        "locked": True,
                        "locked_by": info.get("user_email"),
                        "acquired_at": info.get("acquired_at"),
                        "is_mine": info.get("user_email") == request.user.email,
                    }
                )
            return Response({"locked": False})

        if request.method == "POST":
            acquired = WorkflowService.acquire_editing_lock(
                workflow_id=wid, tenant_id=tenant_id, user=request.user
            )
            if acquired:
                return Response({"status": "acquired"})

            lock_info = WorkflowService.get_lock_info(
                workflow_id=wid, tenant_id=tenant_id
            )
            return Response(
                {
                    "status": "locked",
                    "locked_by": (lock_info.get("user_email") if lock_info else None),
                    "acquired_at": (
                        lock_info.get("acquired_at") if lock_info else None
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        # DELETE
        released = WorkflowService.release_editing_lock(
            workflow_id=wid, tenant_id=tenant_id, user=request.user
        )
        if released:
            return Response({"status": "released"})

        return Response(
            {"error": "Lock held by another user"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # ── Templates (Phase 2) ──

    @action(detail=False, methods=["get"], url_path="templates")
    def templates(self, request):
        """Return system templates (seed manifests)."""
        from orchestration.serializers import PipelineManifestSerializer

        templates = WorkflowService.get_templates()
        serializer = PipelineManifestSerializer(templates, many=True)
        return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def agent_catalog(request):
    """Return the agent catalog with metadata."""
    catalog = WorkflowService.get_agent_catalog()
    serializer = AgentCatalogSerializer(catalog, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def link_from_chat(request):
    """Link a chat-dispatched job to a workspace workflow."""
    serializer = ChatLinkSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        job = AnalysisJob.objects.get(job_id=data["job_id"])
    except AnalysisJob.DoesNotExist:
        return Response(
            {"error": "Job not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    tenant = getattr(request, "tenant", None)
    try:
        link = WorkflowService.link_from_chat(
            job=job,
            chat_session_id=data["chat_session_id"],
            tenant=tenant,
        )
    except ValueError as exc:
        return Response(
            {"error": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "workflow_id": str(link.workflow.workflow_id),
            "snapshot_id": (str(link.snapshot.snapshot_id) if link.snapshot else None),
        },
        status=status.HTTP_201_CREATED,
    )
