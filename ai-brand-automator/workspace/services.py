"""
Service layer for the workspace app.

WorkflowService — business logic for workflow CRUD, execution,
cloning, export/import, chat linking, and agent catalog.
"""

import copy
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import httpx
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from orchestration.models import AnalysisJob, PipelineManifest
from orchestration.tasks import dispatch_job_task

from .models import ChatWorkspaceLink, UserWorkflow, WorkflowSnapshot

logger = logging.getLogger(__name__)

# Agent catalog: internal handlers + external services.
# Mirrors pipeline-orchestrator-svc/app/factory/node_registry.py.
INTERNAL_AGENTS = [
    {
        "id": "router",
        "name": "RouterNode",
        "label": "Intent Router",
        "description": "Routes prompts to the correct pipeline based on intent",
        "type": "internal",
        "handler": "RouterNode",
        "icon": "route",
    },
    {
        "id": "manager",
        "name": "ManagerNode",
        "label": "Pipeline Manager",
        "description": "Aggregates agent outputs into final result_data",
        "type": "internal",
        "handler": "ManagerNode",
        "icon": "layout-dashboard",
    },
    {
        "id": "strategy",
        "name": "StrategyNode",
        "label": "Brand Strategy",
        "description": "Brand strategy analysis and positioning",
        "type": "internal",
        "handler": "StrategyNode",
        "icon": "target",
    },
    {
        "id": "report",
        "name": "ReportNode",
        "label": "Report Generator",
        "description": "Generates executive summary reports",
        "type": "internal",
        "handler": "ReportNode",
        "icon": "file-text",
    },
    {
        "id": "audience",
        "name": "AudienceNode",
        "label": "Audience Analysis",
        "description": "Audience demographics and segmentation",
        "type": "internal",
        "handler": "AudienceNode",
        "icon": "users",
    },
    {
        "id": "planner",
        "name": "PlannerNode",
        "label": "Content Planner",
        "description": "Content planning and editorial strategy",
        "type": "internal",
        "handler": "PlannerNode",
        "icon": "calendar",
    },
    {
        "id": "calendar",
        "name": "CalendarNode",
        "label": "Editorial Calendar",
        "description": "Generates editorial calendar schedules",
        "type": "internal",
        "handler": "CalendarNode",
        "icon": "calendar-days",
    },
]

EXTERNAL_AGENTS = [
    {
        "id": "discovery",
        "name": "discovery",
        "label": "Web Discovery",
        "description": "Web research via Tavily search engine",
        "type": "external",
        "url": "http://discovery-agent-svc:8020/v1/execute",
        "icon": "search",
    },
    {
        "id": "market_research",
        "name": "market_research",
        "label": "Market Research",
        "description": "Market sizing, TAM/SAM/SOM analysis",
        "type": "external",
        "url": "http://market-research-agent-svc:8021/v1/execute",
        "icon": "bar-chart-3",
    },
    {
        "id": "competitor_intelligence",
        "name": "competitor_intelligence",
        "label": "Competitor Intel",
        "description": "Competitor profiling, SWOT, benchmarking",
        "type": "external",
        "url": "http://competitor-intel-agent-svc:8022/v1/execute",
        "icon": "swords",
    },
    {
        "id": "audience_persona",
        "name": "audience_persona",
        "label": "Audience Persona",
        "description": "Buyer persona profiling and journey mapping",
        "type": "external",
        "url": "http://audience-persona-agent-svc:8023/v1/execute",
        "icon": "user-search",
    },
    {
        "id": "trend_cultural",
        "name": "trend_cultural",
        "label": "Trend & Cultural",
        "description": "Trend monitoring, cultural insights, opportunity alerts",
        "type": "external",
        "url": "http://trend-cultural-agent-svc:8024/v1/execute",
        "icon": "trending-up",
    },
    {
        "id": "voice_of_customer",
        "name": "voice_of_customer",
        "label": "Voice of Customer",
        "description": "VoC analysis, sentiment, NPS, pain points",
        "type": "external",
        "url": "http://voc-agent-svc:8025/v1/execute",
        "icon": "message-circle",
    },
    {
        "id": "intelligence",
        "name": "intelligence",
        "label": "Brand Valuation",
        "description": "ISO 10668 brand equity valuation",
        "type": "external",
        "url": "http://intelligence-agent-svc:8030/v1/execute",
        "icon": "gem",
    },
    {
        "id": "content",
        "name": "content",
        "label": "Content Author",
        "description": "SEO/AEO/GEO blog authoring",
        "type": "external",
        "url": "http://content-agent-svc:8050/v1/execute",
        "icon": "pen-tool",
    },
    {
        "id": "social",
        "name": "social",
        "label": "Social Promoter",
        "description": "Social media content adaptation and publishing",
        "type": "external",
        "url": "http://social-agent-svc:8060/v1/execute",
        "icon": "share-2",
    },
    {
        "id": "rag_uploader",
        "name": "rag_uploader",
        "label": "RAG Uploader",
        "description": "Archive documents to Vertex AI RAG",
        "type": "external",
        "url": "http://rag-uploader-agent-svc:8070/v1/execute",
        "icon": "database",
    },
    {
        "id": "odoo_worker",
        "name": "odoo_worker",
        "label": "Odoo Worker",
        "description": "Multi-persona ERP operations via Odoo",
        "type": "external",
        "url": "http://odoo-worker-agent:8100/v1/execute",
        "icon": "briefcase",
    },
    {
        "id": "brand_positioning",
        "name": "brand_positioning",
        "label": "Brand Positioning",
        "description": (
            "Strategic brand positioning, differentiation, "
            "messaging architecture, perceptual mapping"
        ),
        "type": "external",
        "url": "http://brand-positioning-agent-svc:8031/v1/execute",
        "icon": "target",
    },
    {
        "id": "brand_architecture",
        "name": "brand_architecture",
        "label": "Brand Architecture",
        "description": (
            "Brand architecture design, hierarchy tree, naming "
            "conventions, portfolio growth strategy"
        ),
        "type": "external",
        "url": "http://brand-architecture-agent-svc:8032/v1/execute",
        "icon": "git-branch",
    },
]


# Maximum concurrent running jobs per tenant (PG-04)
MAX_CONCURRENT_JOBS = 3


class WorkflowService:
    """Business logic for workflow management."""

    @staticmethod
    @transaction.atomic
    def create_workflow(name, description, manifest_data, layout_data, tenant, user):
        """Create a new workflow with a dedicated PipelineManifest."""
        pipeline_id = f"workspace-{uuid.uuid4().hex[:8]}"
        manifest = PipelineManifest.objects.create(
            pipeline_id=pipeline_id,
            name=name,
            description=description,
            manifest_data=manifest_data,
            tenant=tenant,
            created_by=user,
        )
        workflow = UserWorkflow.objects.create(
            name=name,
            description=description,
            manifest=manifest,
            layout_data=layout_data or {},
            source=UserWorkflow.Source.CREATED,
            tenant=tenant,
            created_by=user,
        )
        return workflow

    @staticmethod
    def execute_workflow(workflow, input_prompt, input_context, user):
        """Execute a workflow: create job, freeze snapshot, dispatch.

        Returns the created AnalysisJob.
        Raises ValueError if concurrent limit exceeded (PG-04).
        """
        tenant = workflow.tenant

        # PG-04: Check concurrent execution limit
        WorkflowService.check_concurrent_limit(tenant)

        # Create AnalysisJob
        job = AnalysisJob.objects.create(
            manifest=workflow.manifest,
            input_prompt=input_prompt,
            input_context=input_context or {},
            tenant=tenant,
            created_by=user,
            status=AnalysisJob.Status.QUEUED,
        )

        # Freeze snapshot
        WorkflowSnapshot.objects.create(
            workflow=workflow,
            job=job,
            manifest_snapshot=workflow.manifest.manifest_data,
            layout_snapshot=workflow.layout_data,
            tenant=tenant,
        )

        # Update execution metadata
        workflow.last_executed_at = timezone.now()
        workflow.execution_count = (workflow.execution_count or 0) + 1
        workflow.save(
            update_fields=[
                "last_executed_at",
                "execution_count",
                "updated_at",
            ]
        )

        # Dispatch via Celery (same path as chat/pipelines)
        dispatch_job_task.delay(job.id)
        logger.info(
            "Workflow %s executed — job %s queued",
            workflow.workflow_id,
            job.job_id,
        )

        return job

    @staticmethod
    @transaction.atomic
    def clone_workflow(source_workflow, new_name, tenant, user):
        """Deep-copy a workflow: clone manifest + create new workflow."""
        # Clone the manifest
        source_manifest = source_workflow.manifest
        new_pipeline_id = f"workspace-{uuid.uuid4().hex[:8]}"
        new_manifest = PipelineManifest.objects.create(
            pipeline_id=new_pipeline_id,
            name=new_name,
            description=source_manifest.description,
            manifest_data=copy.deepcopy(source_manifest.manifest_data),
            tenant=tenant,
            created_by=user,
        )

        # Clone the workflow
        new_workflow = UserWorkflow.objects.create(
            name=new_name,
            description=source_workflow.description,
            manifest=new_manifest,
            layout_data=copy.deepcopy(source_workflow.layout_data),
            source=UserWorkflow.Source.CLONED,
            tenant=tenant,
            created_by=user,
        )
        return new_workflow

    @staticmethod
    def export_workflow(workflow):
        """Export a workflow as sanitized JSON (OG-05).

        Strips tenant_id, user info, and internal service URLs.
        """
        manifest_data = copy.deepcopy(
            workflow.manifest.manifest_data if workflow.manifest else {}
        )

        # Replace internal URLs with placeholders
        for node in manifest_data.get("nodes", []):
            if node.get("type") == "external" and "url" in node:
                node["url"] = "{{SERVICE_URL}}"

        return {
            "name": workflow.name,
            "description": workflow.description,
            "manifest_data": manifest_data,
            "layout_data": workflow.layout_data,
            "source": workflow.source,
            "exported_at": timezone.now().isoformat(),
        }

    @staticmethod
    @transaction.atomic
    def import_workflow(name, description, manifest_data, layout_data, tenant, user):
        """Import a workflow from validated JSON.

        Resolves {{SERVICE_URL}} placeholders to actual service URLs.
        """
        # Resolve placeholders
        resolved_data = copy.deepcopy(manifest_data)
        for node in resolved_data.get("nodes", []):
            if node.get("type") == "external" and node.get("url") == "{{SERVICE_URL}}":
                # Look up from EXTERNAL_AGENTS
                agent = next(
                    (a for a in EXTERNAL_AGENTS if a["name"] == node["id"]),
                    None,
                )
                if agent:
                    node["url"] = agent["url"]

        pipeline_id = f"workspace-import-{uuid.uuid4().hex[:8]}"
        manifest = PipelineManifest.objects.create(
            pipeline_id=pipeline_id,
            name=name,
            description=description,
            manifest_data=resolved_data,
            tenant=tenant,
            created_by=user,
        )
        workflow = UserWorkflow.objects.create(
            name=name,
            description=description,
            manifest=manifest,
            layout_data=layout_data or {},
            source=UserWorkflow.Source.CREATED,
            tenant=tenant,
            created_by=user,
        )
        return workflow

    @staticmethod
    @transaction.atomic
    def link_from_chat(job, chat_session_id, tenant):
        """Link a chat-dispatched job to a workspace workflow.

        Creates UserWorkflow + WorkflowSnapshot + ChatWorkspaceLink.
        """
        # Check if link already exists
        existing = ChatWorkspaceLink.objects.filter(job=job).first()
        if existing:
            return existing

        # Create or find a workflow for this manifest
        manifest = job.manifest
        if not manifest:
            raise ValueError("Cannot link job without a manifest")

        # Try to find existing workflow for this manifest
        workflow = UserWorkflow.objects.filter(
            manifest=manifest, tenant=tenant, is_active=True
        ).first()

        if not workflow:
            workflow = UserWorkflow.objects.create(
                name=manifest.name or f"Chat Workflow {job.job_id}",
                description=manifest.description or "",
                manifest=manifest,
                source=UserWorkflow.Source.CHAT,
                tenant=tenant,
                created_by=job.created_by,
            )

        # Create snapshot
        snapshot = WorkflowSnapshot.objects.create(
            workflow=workflow,
            job=job,
            manifest_snapshot=manifest.manifest_data,
            layout_snapshot=workflow.layout_data,
            summary=(
                WorkflowService.extract_dashboard_data(job.result_data)
                if job.result_data
                else {}
            ),
            dashboard_data=(
                WorkflowService.extract_dashboard_data(job.result_data)
                if job.result_data
                else {}
            ),
            tenant=tenant,
        )

        # Create the link
        link = ChatWorkspaceLink.objects.create(
            job=job,
            workflow=workflow,
            snapshot=snapshot,
            chat_session_id=chat_session_id,
            tenant=tenant,
        )
        return link

    @staticmethod
    def extract_dashboard_data(result_data):
        """Extract hybrid dashboard data from pipeline result_data.

        Returns: {typed: {voc_health_score, nps, ...}, generic: {k: v}}
        """
        if not result_data:
            return {"typed": {}, "generic": {}}

        typed = {}
        generic = {}
        node_results = result_data.get("node_results", {})

        # VoC metrics
        voca = node_results.get("voice_of_customer", {})
        if not voca:
            voca = result_data if result_data.get("voc_health_score") else {}
        if voca:
            if voca.get("voc_health_score") is not None:
                typed["voc_health_score"] = voca["voc_health_score"]
            nps = voca.get("nps_analysis", {})
            if isinstance(nps, dict):
                current = nps.get("current_nps", nps.get("proxy_nps", {}))
                if isinstance(current, dict) and current.get("nps_score") is not None:
                    typed["nps"] = current["nps_score"]
            sentiment = voca.get("sentiment", {})
            if isinstance(sentiment, dict):
                overall = sentiment.get("overall_sentiment", {})
                if isinstance(overall, dict):
                    typed["sentiment_trend"] = (
                        "positive"
                        if overall.get("positive", 0) > 0.5
                        else (
                            "negative"
                            if overall.get("negative", 0) > 0.3
                            else "neutral"
                        )
                    )
            pain_matrix = voca.get("pain_point_priority_matrix", {})
            if isinstance(pain_matrix, dict):
                typed["pain_points_count"] = len(pain_matrix.get("pain_points", []))

        # Trend metrics
        tcia = node_results.get("trend_cultural", {})
        if not tcia:
            tcia = result_data if result_data.get("scored_trends") else {}
        if tcia:
            scored = tcia.get("scored_trends", [])
            typed["trends_identified"] = len(scored)

        # Confidence score (from various agents)
        for agent_key in (
            "voice_of_customer",
            "trend_cultural",
            "competitor_intelligence",
            "audience_persona",
        ):
            agent_data = node_results.get(agent_key, {})
            if agent_data.get("confidence_score"):
                typed["confidence_score"] = agent_data["confidence_score"]
                break

        # Data coverage
        coverage = result_data.get("data_coverage_pct")
        if coverage is not None:
            typed["data_coverage_pct"] = coverage

        # Collect remaining top-level keys as generic
        skip_keys = {"node_results", "final_response", "summary"}
        for key, value in result_data.items():
            if key not in skip_keys and not isinstance(value, dict):
                generic[key] = value

        return {"typed": typed, "generic": generic}

    # Cache key prefix and TTL for agent health checks
    HEALTH_CACHE_PREFIX = "workspace:agent_health"
    HEALTH_CACHE_TTL = 60  # seconds
    HEALTH_CHECK_TIMEOUT = 3  # seconds per request

    @staticmethod
    def _health_cache_key(agent_id):
        return f"{WorkflowService.HEALTH_CACHE_PREFIX}:{agent_id}"

    @staticmethod
    def _derive_health_url(execute_url):
        """Derive /health URL from an agent's /v1/execute URL."""
        parsed = urlparse(execute_url)
        return f"{parsed.scheme}://{parsed.netloc}/health"

    @staticmethod
    def _check_single_agent_health(agent_id, health_url):
        """Check health of a single external agent. Returns (agent_id, status)."""
        try:
            resp = httpx.get(health_url, timeout=WorkflowService.HEALTH_CHECK_TIMEOUT)
            return (agent_id, "healthy" if resp.status_code == 200 else "unhealthy")
        except Exception:
            return (agent_id, "unhealthy")

    @staticmethod
    def get_agent_catalog():
        """Return agent catalog with health status.

        Internal agents are always 'healthy'. External agents are
        health-checked via their /health endpoint with a 60s Redis cache.
        """
        catalog = []

        # Internal agents — always healthy (in-process handlers)
        for agent in INTERNAL_AGENTS:
            entry = agent.copy()
            entry["health"] = "healthy"
            catalog.append(entry)

        # External agents — check cache, then fetch uncached in parallel
        uncached = []
        for agent in EXTERNAL_AGENTS:
            entry = agent.copy()
            cached = cache.get(WorkflowService._health_cache_key(agent["id"]))
            if cached is not None:
                entry["health"] = cached
            else:
                entry["health"] = "unknown"  # placeholder, updated below
                uncached.append(agent)
            catalog.append(entry)

        # Parallel health checks for uncached agents
        if uncached:
            results = {}
            try:
                with ThreadPoolExecutor(max_workers=min(len(uncached), 10)) as pool:
                    futures = {
                        pool.submit(
                            WorkflowService._check_single_agent_health,
                            agent["id"],
                            WorkflowService._derive_health_url(agent["url"]),
                        ): agent["id"]
                        for agent in uncached
                    }
                    for future in as_completed(futures, timeout=5):
                        try:
                            agent_id, status = future.result()
                            results[agent_id] = status
                        except Exception:
                            results[futures[future]] = "unhealthy"
            except Exception:
                logger.warning("Agent health check pool failed", exc_info=True)

            # Update catalog entries + cache
            for entry in catalog:
                if entry["id"] in results:
                    entry["health"] = results[entry["id"]]
                    cache.set(
                        WorkflowService._health_cache_key(entry["id"]),
                        results[entry["id"]],
                        WorkflowService.HEALTH_CACHE_TTL,
                    )

        return catalog

    @staticmethod
    def check_concurrent_limit(tenant):
        """PG-04: Enforce max concurrent running jobs per tenant.

        Raises ValueError if the limit is exceeded.
        """
        if not tenant:
            return

        running_count = AnalysisJob.objects.filter(
            tenant=tenant,
            status__in=[
                AnalysisJob.Status.QUEUED,
                AnalysisJob.Status.RUNNING,
            ],
        ).count()

        if running_count >= MAX_CONCURRENT_JOBS:
            raise ValueError(
                f"Concurrent execution limit reached "
                f"({MAX_CONCURRENT_JOBS} jobs). "
                f"Wait for a running job to complete."
            )

    @staticmethod
    def get_templates():
        """Return system templates (seed manifests with tenant=NULL)."""
        return PipelineManifest.objects.filter(
            tenant__isnull=True,
            is_active=True,
        ).order_by("name")

    @staticmethod
    @transaction.atomic
    def update_workflow(workflow, validated_data):
        """Update a workflow's manifest and/or metadata."""
        manifest_data = validated_data.pop("manifest_data", None)

        if manifest_data is not None:
            workflow.manifest.manifest_data = manifest_data
            workflow.manifest.save(update_fields=["manifest_data", "updated_at"])

        update_fields = ["updated_at"]
        for field in ("name", "description", "layout_data", "is_favorite"):
            if field in validated_data:
                setattr(workflow, field, validated_data[field])
                update_fields.append(field)
                if field == "name":
                    workflow.manifest.name = validated_data["name"]
                    workflow.manifest.save(update_fields=["name", "updated_at"])

        workflow.save(update_fields=update_fields)
        return workflow

    # ── Editing Lock (Phase 2) ──

    LOCK_TTL = 7200  # 2 hours

    @staticmethod
    def _lock_key(tenant_id, workflow_id):
        return f"workspace:{tenant_id}:editing:{workflow_id}"

    @staticmethod
    def acquire_editing_lock(workflow_id, tenant_id, user):
        """Acquire an editing lock. Returns True if acquired.

        Uses Django cache (Redis-backed). The lock stores the user's email
        and a timestamp. TTL is 2 hours.
        """
        key = WorkflowService._lock_key(tenant_id, workflow_id)
        existing = cache.get(key)

        if existing:
            # If the same user already holds the lock, refresh TTL
            if existing.get("user_email") == user.email:
                cache.set(key, existing, WorkflowService.LOCK_TTL)
                return True
            return False

        lock_data = {
            "user_email": user.email,
            "user_id": user.id,
            "acquired_at": timezone.now().isoformat(),
        }
        cache.set(key, lock_data, WorkflowService.LOCK_TTL)
        return True

    @staticmethod
    def release_editing_lock(workflow_id, tenant_id, user):
        """Release an editing lock. Only the holder can release.

        Returns True if released, False if not the holder.
        """
        key = WorkflowService._lock_key(tenant_id, workflow_id)
        existing = cache.get(key)

        if not existing:
            return True  # Already unlocked

        if existing.get("user_email") == user.email:
            cache.delete(key)
            return True

        return False

    @staticmethod
    def force_release_lock(workflow_id, tenant_id):
        """Force-release a lock (ADMIN only). Always succeeds."""
        key = WorkflowService._lock_key(tenant_id, workflow_id)
        cache.delete(key)
        return True

    @staticmethod
    def get_lock_info(workflow_id, tenant_id):
        """Get lock info. Returns dict or None if unlocked."""
        key = WorkflowService._lock_key(tenant_id, workflow_id)
        return cache.get(key)
