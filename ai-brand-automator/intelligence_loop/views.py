"""
Views for the Intelligence Loop app.

Three groups of endpoints:

1. JWT-authenticated UI endpoints (Intelligence Feed):
   - GET    /intelligence-reports/
   - GET    /intelligence-reports/<id>/
   - POST   /learnings/<id>/apply/      (EDITOR)
   - POST   /learnings/<id>/dismiss/    (EDITOR)
   - POST   /learnings/<id>/save/       (EDITOR)
   - GET    /wf2-rerun-requests/        (ADMIN/OWNER)
   - POST   /wf2-rerun-requests/<id>/approve/ (ADMIN/OWNER)
   - POST   /wf2-rerun-requests/<id>/reject/  (ADMIN/OWNER)
   - POST   /trigger/                    (EDITOR — proxy to ILA service)

2. Service-token ingest endpoints (called by ILA microservice):
   - POST   /ingest/intelligence-report/
   - POST   /ingest/rag-learning/
   - POST   /ingest/wf2-request/
"""

import logging
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from optimization.models import CampaignRegistry
from orchestration.models import AnalysisJob, PipelineManifest

from .models import (
    CampaignIntelligence,
    LearningDocument,
    LearningRecord,
    WF2RerunRequest,
)
from .permissions import (
    HasILAServiceToken,
    IsTenantAdmin,
    IsTenantEditor,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)
from .serializers import (
    ApplyLearningSerializer,
    AutoTriggerSerializer,
    CampaignIntelligenceDetailSerializer,
    CampaignIntelligenceListSerializer,
    IngestIntelligenceReportSerializer,
    IngestRagLearningSerializer,
    IngestWF2RequestSerializer,
    LearningDocumentSerializer,
    LearningRecordSerializer,
    RejectWF2RequestSerializer,
    TriggerExtractionSerializer,
    WF2RerunRequestSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tenant_filter(qs, request):
    """Defensive multi-tenant filter (CLAUDE.md pattern)."""
    tenant = getattr(request, "tenant", None)
    if tenant:
        return qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
    return qs.filter(tenant__isnull=True)


# WF1 agent code → pipeline_id used by Django to dispatch a re-run.
WF1_AGENT_TO_PIPELINE = {
    "APA": "audience-persona",
    "CIA": "competitor-intelligence",
    "MRA": "market-research",
    "TCIA": "trend-cultural-insights",
    "VOC": "voice-of-customer",
}

# WF2 agent code → pipeline_id.
WF2_AGENT_TO_PIPELINE = {
    "BPA": "brand-strategy-positioning",
    "BAA": "brand-strategy-architecture",
    "BPV": "brand-strategy-personality",
    "NTA": "brand-strategy-naming",
    "BSA": "brand-strategy-story",
}

# WF3 agent code → pipeline_id (used by ILA auto-trigger).
WF3_AGENT_TO_PIPELINE = {
    "CAA": "meta-campaign-architecture",
    "CGA": "meta-creative-generation",
    "APA33": "meta-ad-publishing",
}


def _dispatch_rerun(*, tenant, user, pipeline_id, learning, note=""):
    """
    Create an AnalysisJob for a re-run with ILA learning context, then
    dispatch via OrchestratorDispatcher.  Also creates a UserWorkflow +
    WorkflowSnapshot so the execution appears in the Workflow Workspace.

    Returns the created AnalysisJob (or None on failure).
    """
    from orchestration.services import OrchestratorDispatcher
    from workspace.models import UserWorkflow, WorkflowSnapshot

    manifest = (
        PipelineManifest.objects.filter(pipeline_id=pipeline_id)
        .order_by("-version")
        .first()
    )

    if not manifest:
        logger.error(
            "ILA re-run dispatch: no PipelineManifest for pipeline_id=%s",
            pipeline_id,
        )
        return None

    input_prompt = (
        f"ILA-triggered re-run for learning '{learning.headline}'. " f"{note}".strip()
    )

    job = AnalysisJob.objects.create(
        tenant=tenant,
        created_by=user,
        manifest=manifest,
        input_prompt=input_prompt,
        input_context={
            "pipeline_id": pipeline_id,
            "ila_learning_context": {
                "learning_id": str(learning.learning_id),
                "category": learning.category,
                "headline": learning.headline,
                "detail": learning.detail,
                "confidence": learning.confidence,
                "impact": learning.impact,
                "target_workflow": learning.target_workflow,
                "target_agent": learning.target_agent,
                "intelligence_id": str(learning.intelligence.intelligence_id),
                "campaign_id": str(learning.intelligence.campaign.campaign_id),
            },
            "trigger_source": "intelligence_loop",
        },
    )

    # Create a UserWorkflow + WorkflowSnapshot so the execution appears
    # in the Workflow Workspace with live progress tracking.
    try:
        workflow = UserWorkflow.objects.create(
            name=f"ILA Re-run: {learning.headline[:80]}",
            description=input_prompt,
            manifest=manifest,
            layout_data={},
            source=UserWorkflow.Source.CREATED,
            tenant=tenant,
            created_by=user,
            last_executed_at=timezone.now(),
            execution_count=1,
        )
        WorkflowSnapshot.objects.create(
            workflow=workflow,
            job=job,
            manifest_snapshot=manifest.manifest_data,
            layout_snapshot={},
            tenant=tenant,
        )
    except Exception as exc:
        logger.warning("ILA re-run: failed to create workspace workflow: %s", exc)

    dispatched = OrchestratorDispatcher().dispatch(job)
    if not dispatched:
        logger.warning(
            "ILA re-run dispatch failed for job %s (pipeline %s)",
            job.job_id,
            pipeline_id,
        )
    return job


# ---------------------------------------------------------------------------
# Read viewset
# ---------------------------------------------------------------------------


class CampaignIntelligenceViewSet(
    RoleBasedPermissionMixin, viewsets.ReadOnlyModelViewSet
):
    """List and retrieve CampaignIntelligence rows for the Intelligence Feed."""

    serializer_class = CampaignIntelligenceDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "intelligence_id"

    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
    }

    def get_queryset(self):
        qs = CampaignIntelligence.objects.select_related(
            "campaign", "tenant"
        ).prefetch_related("learnings")
        qs = _tenant_filter(qs, self.request)
        campaign = self.request.query_params.get("campaign")
        if campaign:
            qs = qs.filter(campaign__campaign_id=campaign)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return CampaignIntelligenceListSerializer
        return CampaignIntelligenceDetailSerializer


# ---------------------------------------------------------------------------
# Learning action endpoints
# ---------------------------------------------------------------------------


def _get_user_learning(request, learning_id):
    qs = LearningRecord.objects.select_related("intelligence", "intelligence__campaign")
    qs = _tenant_filter(qs, request)
    return get_object_or_404(qs, learning_id=learning_id)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def apply_learning(request, learning_id):
    """Manually apply a learning by dispatching its target re-run.

    WF1 + WF3 dispatches happen immediately.
    WF2 dispatches are blocked here — caller should use the WF2RerunRequest
    flow because WF2 always requires ADMIN/OWNER approval (design §8.2).
    """
    serializer = ApplyLearningSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    note = serializer.validated_data.get("note", "")

    learning = _get_user_learning(request, learning_id)

    if learning.target_workflow == "WF2":
        return Response(
            {
                "detail": (
                    "WF2 learnings require ADMIN/OWNER approval. "
                    "Submit a WF2RerunRequest instead."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if learning.target_workflow == "WF1":
        pipeline_id = WF1_AGENT_TO_PIPELINE.get(learning.target_agent.upper())
    else:
        # WF3 — only campaign architecture is re-runnable today.
        pipeline_id = "meta-campaign-architecture"

    if not pipeline_id:
        return Response(
            {"detail": (f"No pipeline mapping for agent '{learning.target_agent}'.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    job = _dispatch_rerun(
        tenant=getattr(request, "tenant", None),
        user=request.user,
        pipeline_id=pipeline_id,
        learning=learning,
        note=note,
    )
    if job is None:
        return Response(
            {"detail": "Re-run dispatch failed."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    learning.status = "applied"
    learning.save(update_fields=["status", "updated_at"])

    return Response(
        {
            "learning_id": str(learning.learning_id),
            "status": learning.status,
            "job_id": str(job.job_id),
            "pipeline_id": pipeline_id,
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def dismiss_learning(request, learning_id):
    learning = _get_user_learning(request, learning_id)
    learning.status = "dismissed"
    learning.save(update_fields=["status", "updated_at"])
    return Response(LearningRecordSerializer(learning).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def save_learning(request, learning_id):
    learning = _get_user_learning(request, learning_id)
    learning.status = "saved"
    learning.save(update_fields=["status", "updated_at"])
    return Response(LearningRecordSerializer(learning).data)


# ---------------------------------------------------------------------------
# WF2 approval queue (ADMIN/OWNER)
# ---------------------------------------------------------------------------


class WF2RerunRequestViewSet(RoleBasedPermissionMixin, viewsets.ReadOnlyModelViewSet):
    """List + retrieve pending WF2 re-run approval requests."""

    serializer_class = WF2RerunRequestSerializer
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    lookup_field = "request_id"

    role_permissions = {
        "list": [IsAuthenticated, IsTenantAdmin],
        "retrieve": [IsAuthenticated, IsTenantAdmin],
    }

    def get_queryset(self):
        qs = WF2RerunRequest.objects.select_related("learning", "decided_by", "tenant")
        qs = _tenant_filter(qs, self.request)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


def _get_user_wf2_request(request, request_id):
    qs = WF2RerunRequest.objects.select_related(
        "learning", "learning__intelligence", "learning__intelligence__campaign"
    )
    qs = _tenant_filter(qs, request)
    return get_object_or_404(qs, request_id=request_id)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def approve_wf2_request(request, request_id):
    wf2_req = _get_user_wf2_request(request, request_id)

    if wf2_req.status != "pending":
        return Response(
            {"detail": f"Request is already {wf2_req.status}."},
            status=status.HTTP_409_CONFLICT,
        )
    if wf2_req.is_expired:
        wf2_req.status = "expired"
        wf2_req.save(update_fields=["status", "updated_at"])
        return Response(
            {"detail": "Request has expired."},
            status=status.HTTP_410_GONE,
        )

    pipeline_id = WF2_AGENT_TO_PIPELINE.get(wf2_req.requested_agent.upper())
    if not pipeline_id:
        return Response(
            {
                "detail": (
                    f"No WF2 pipeline mapping for agent "
                    f"'{wf2_req.requested_agent}'."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    job = _dispatch_rerun(
        tenant=getattr(request, "tenant", None),
        user=request.user,
        pipeline_id=pipeline_id,
        learning=wf2_req.learning,
        note=f"Approved by {request.user.email} via WF2 approval flow.",
    )
    if job is None:
        return Response(
            {"detail": "Re-run dispatch failed."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    with transaction.atomic():
        wf2_req.status = "approved"
        wf2_req.decided_by = request.user
        wf2_req.decided_at = timezone.now()
        wf2_req.job_id = str(job.job_id)
        wf2_req.save(
            update_fields=[
                "status",
                "decided_by",
                "decided_at",
                "job_id",
                "updated_at",
            ]
        )
        wf2_req.learning.status = "applied"
        wf2_req.learning.save(update_fields=["status", "updated_at"])

    return Response(WF2RerunRequestSerializer(wf2_req).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def reject_wf2_request(request, request_id):
    wf2_req = _get_user_wf2_request(request, request_id)
    if wf2_req.status != "pending":
        return Response(
            {"detail": f"Request is already {wf2_req.status}."},
            status=status.HTTP_409_CONFLICT,
        )

    serializer = RejectWF2RequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    wf2_req.status = "rejected"
    wf2_req.decided_by = request.user
    wf2_req.decided_at = timezone.now()
    wf2_req.rejection_reason = serializer.validated_data.get("reason", "")
    wf2_req.save(
        update_fields=[
            "status",
            "decided_by",
            "decided_at",
            "rejection_reason",
            "updated_at",
        ]
    )
    return Response(WF2RerunRequestSerializer(wf2_req).data)


# ---------------------------------------------------------------------------
# Manual trigger (UI → ILA microservice proxy)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def trigger_extraction(request):
    """Proxy "Re-extract now" UI button to the ILA microservice."""
    serializer = TriggerExtractionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data

    tenant = getattr(request, "tenant", None)
    campaign_qs = CampaignRegistry.objects.all()
    if tenant is not None:
        campaign_qs = campaign_qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
    campaign = get_object_or_404(
        campaign_qs,
        campaign_id=payload["campaign_id"],
    )

    ila_url = getattr(
        settings, "ILA_SERVICE_URL", "http://intelligence-loop-agent-svc:8045"
    )
    ila_token = getattr(settings, "ILA_SERVICE_TOKEN", "") or ""

    try:
        resp = requests.post(
            f"{ila_url.rstrip('/')}/v1/execute",
            json={
                "job_id": str(uuid.uuid4()),
                "tenant_id": str(tenant.id) if tenant else "",
                "state": {"campaign_id": str(campaign.campaign_id)},
                "context": {
                    "campaign_id": str(campaign.campaign_id),
                    "trigger_source": "manual",
                },
                "config": {"default_mode": payload["mode"]},
            },
            headers={"X-Service-Token": ila_token},
            timeout=60,
        )
    except requests.RequestException as exc:
        logger.error("ILA trigger proxy failed: %s", exc)
        return Response(
            {"detail": "Intelligence Loop service unreachable."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        {
            "status": "queued" if resp.ok else "error",
            "ila_status_code": resp.status_code,
            "ila_response": resp.json() if resp.content else {},
        },
        status=resp.status_code,
    )


# ---------------------------------------------------------------------------
# Service-token ingest endpoints (called by ILA microservice)
# ---------------------------------------------------------------------------


def _resolve_tenant(tenant_id):
    if not tenant_id:
        return None
    from tenants.models import Tenant

    return Tenant.objects.filter(id=tenant_id).first()


@api_view(["POST"])
@permission_classes([HasILAServiceToken])
def ingest_intelligence_report(request):
    """Persist a CampaignIntelligence row + child LearningRecord rows."""
    serializer = IngestIntelligenceReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    tenant = _resolve_tenant(data.get("tenant_id"))
    campaign = get_object_or_404(CampaignRegistry, campaign_id=data["campaign_id"])

    with transaction.atomic():
        intel = CampaignIntelligence.objects.create(
            tenant=tenant,
            campaign=campaign,
            job_id=data["job_id"],
            mode=data["mode"],
            trigger_source=data["trigger_source"],
            intelligence_report=data.get("intelligence_report", {}),
            auto_reruns_triggered=data.get("auto_reruns_triggered", 0),
            contradictions=data.get("contradictions", []),
            rag_writes=data.get("rag_writes", 0),
            brand_context_id=data.get("brand_context_id", "") or "",
        )

        learnings_out = []
        for entry in data.get("learnings", []):
            learning = LearningRecord.objects.create(
                tenant=tenant,
                intelligence=intel,
                learning_id=entry.get("learning_id") or uuid.uuid4(),
                category=entry["category"],
                headline=entry["headline"],
                detail=entry.get("detail", {}),
                confidence=entry["confidence"],
                impact=entry["impact"],
                target_workflow=entry["target_workflow"],
                target_agent=entry["target_agent"],
            )
            learnings_out.append(learning)

    return Response(
        {
            "intelligence_id": str(intel.intelligence_id),
            "learnings": [str(learning.learning_id) for learning in learnings_out],
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([HasILAServiceToken])
def ingest_rag_learning(request):
    """Persist a LearningDocument row.

    The post_save signal in ``rag_index.signals`` enqueues a Celery task
    to sync this document into the per-tenant Vertex AI data store.
    """
    serializer = IngestRagLearningSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    learning = get_object_or_404(LearningRecord, learning_id=data["learning_id"])
    tenant = _resolve_tenant(data.get("tenant_id")) or learning.tenant

    doc, created = LearningDocument.objects.update_or_create(
        learning=learning,
        defaults={
            "tenant": tenant,
            "content": data["content"],
            "metadata": data.get("metadata", {}),
        },
    )
    return Response(
        LearningDocumentSerializer(doc).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([HasILAServiceToken])
def ingest_wf2_request(request):
    """Persist a pending WF2RerunRequest row."""
    serializer = IngestWF2RequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    learning = get_object_or_404(LearningRecord, learning_id=data["learning_id"])
    tenant = _resolve_tenant(data.get("tenant_id")) or learning.tenant
    expires_at = timezone.now() + timedelta(hours=int(data.get("expires_in_hours", 72)))

    req = WF2RerunRequest.objects.create(
        tenant=tenant,
        learning=learning,
        requested_agent=data["requested_agent"],
        rationale=data["rationale"],
        expires_at=expires_at,
    )
    return Response(
        WF2RerunRequestSerializer(req).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([HasILAServiceToken])
def auto_trigger_rerun(request):
    """Service-token endpoint: ILA requests an auto-trigger re-run.

    WF1/WF3 only — WF2 always goes through ``ingest_wf2_request`` for
    human approval. Returns 400 if the learning targets WF2.
    """
    serializer = AutoTriggerSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    learning = get_object_or_404(
        LearningRecord.objects.select_related("intelligence__campaign", "tenant"),
        learning_id=data["learning_id"],
    )
    if learning.target_workflow == "WF2":
        return Response(
            {"detail": "WF2 learnings require human approval."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_target_agent = (learning.target_agent or "").upper()
    if learning.target_workflow == "WF1":
        pipeline_id = WF1_AGENT_TO_PIPELINE.get(normalized_target_agent)
    else:
        pipeline_id = WF3_AGENT_TO_PIPELINE.get(normalized_target_agent)

    if not pipeline_id:
        return Response(
            {
                "detail": (
                    f"No pipeline mapping for {learning.target_workflow} "
                    f"agent {learning.target_agent}"
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    job = _dispatch_rerun(
        tenant=learning.tenant,
        user=None,
        pipeline_id=pipeline_id,
        learning=learning,
        note=data.get("note", ""),
    )
    if not job:
        return Response(
            {"detail": "Dispatch failed"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    learning.status = "applied"
    learning.save(update_fields=["status", "updated_at"])

    return Response(
        {"job_id": str(job.job_id), "pipeline_id": pipeline_id},
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["GET"])
@permission_classes([HasILAServiceToken])
def campaign_context(request, campaign_id):
    """Aggregated campaign context for ILA extraction (Phase 3).

    Returns CampaignRegistry summary, recent OptimizationRecommendations
    (last 30 days, max 50), and a brand profile snippet from the linked
    Company. ILA's extractor uses this as the input for Claude.
    """
    from optimization.models import OptimizationRecommendation

    campaign = get_object_or_404(CampaignRegistry, campaign_id=campaign_id)
    cutoff = timezone.now() - timedelta(days=30)
    recs = OptimizationRecommendation.objects.filter(
        campaign=campaign, created_at__gte=cutoff
    ).order_by("-created_at")[:50]
    company = campaign.company
    company_snippet = {}
    if company:
        company_snippet = {
            "name": company.name or "",
            "industry": company.industry or "",
            "brand_voice": company.brand_voice or "",
            "target_audience": company.target_audience or "",
            "vision_statement": getattr(company, "vision_statement", "") or "",
            "mission_statement": getattr(company, "mission_statement", "") or "",
            "positioning_statement": (
                getattr(company, "positioning_statement", "") or ""
            ),
            "value_proposition": getattr(company, "value_proposition", "") or "",
        }
    return Response(
        {
            "campaign": {
                "campaign_id": str(campaign.campaign_id),
                "meta_campaign_id": campaign.meta_campaign_id,
                "campaign_name": campaign.campaign_name,
                "objective": campaign.objective,
                "status": campaign.status,
                "optimization_mode": campaign.optimization_mode,
                "target_cpa_usd": (
                    float(campaign.target_cpa_usd)
                    if campaign.target_cpa_usd is not None
                    else None
                ),
                "target_roas": (
                    float(campaign.target_roas)
                    if campaign.target_roas is not None
                    else None
                ),
                "daily_budget_usd": float(campaign.daily_budget_usd),
                "ad_sets": campaign.ad_sets or [],
                "ads": campaign.ads or [],
            },
            "company": company_snippet,
            "recommendations": [
                {
                    "recommendation_id": str(r.recommendation_id),
                    "action_type": r.action_type,
                    "entity_type": r.entity_type,
                    "rationale": r.rationale,
                    "current_values": r.current_values,
                    "proposed_values": r.proposed_values,
                    "projected_impact": r.projected_impact,
                    "priority": r.priority,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in recs
            ],
        }
    )
