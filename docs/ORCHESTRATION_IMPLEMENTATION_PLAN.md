# Orchestration App — Implementation Plan (core-api-service)

> Created: 2026-02-17
> Updated: 2026-02-17 (HLD v6.0 alignment — System Architecture, Service Contracts, Intent Routing, Tenant Context)
> Status: **📋 Pending Approval**
> Branch: `feature/implement-core-api-service`
> Design Doc: "Unified Detailed Design: core-api-service (v6.0)" + "High-Level Design: Generic AI Agent Orchestration Infrastructure (v6.0)"

---

## Executive Summary

**What we're building**: A new `orchestration` Django app that serves as the command-and-control layer for the AI Multi-Agent Pipeline. Users submit natural language analysis prompts, the system dispatches them to an external `pipeline-orchestrator-svc` (LangGraph-based), and streams progress/results back to the frontend.

**What it is NOT**: This is NOT the pipeline-orchestrator-svc itself (that's a separate Python/LangGraph microservice). This is the Django API layer that:
1. Stores pipeline manifest definitions (what agents to run, in what order)
2. Accepts analysis job requests from the frontend
3. Dispatches jobs to the external orchestrator
4. Receives callbacks with progress updates and results
5. Serves job status and results to the frontend

**Architecture Decision**: **Standard Django pattern** (NOT Hexagonal Architecture). The orchestration app is an API/command layer with REST endpoints and a thin service class — it doesn't have complex domain logic, ports, or adapters like the data_ingestion/media_curation pipeline apps. The closest existing pattern is `automation/` (ViewSets + service classes).

**Directory Decision**: **Option A — Hybrid Monolith + Microservices**. The `orchestration` app lives inside the existing `ai-brand-automator/` Django project (same as all implemented services). Future services that require different stacks (LangGraph, Playwright, Pandas) will be created as **separate top-level directories** in the workspace.

---

## Workspace Directory Structure (Option A — Hybrid)

The HLD v6.0 defines logical service names. This section maps each to its **actual directory** in the workspace.

```
Prevision_WS/
├── ai-brand-automator/                    # Django project = core-api-service + data cluster
│   ├── brand_automator/                   # Project settings, middleware, auth
│   │   ├── settings.py                    # SHARED_APPS, CELERY, ORCHESTRATOR_* env vars
│   │   ├── middleware.py                  # TenantMembershipMiddleware (X-Tenant-ID)
│   │   ├── urls.py                        # /api/v1/* routing
│   │   └── celery.py                      # Task routing (orchestration queue)
│   ├── tenants/                           # ✅ Implemented — Identity & RBAC
│   ├── onboarding/                        # ✅ Implemented — Company profiles
│   ├── automation/                        # ✅ Implemented — Social media
│   ├── files/                             # ✅ Implemented — File management
│   ├── ai_services/                       # ✅ Implemented — Gemini AI
│   ├── subscriptions/                     # ✅ Implemented — Stripe billing
│   ├── data_ingestion/                    # ✅ Implemented — data-ingestion-svc (Hexagonal)
│   ├── media_curation/                    # ✅ Implemented — media-curation-svc (Hexagonal)
│   ├── rag_index/                         # ✅ Implemented — rag-index-svc (Hexagonal)
│   ├── orchestration/                     # 🔄 THIS PLAN — core-api orchestration logic
│   │   ├── models.py                      #    PipelineManifest + AnalysisJob
│   │   ├── serializers.py                 #    Manifest validation, job serialization
│   │   ├── views.py                       #    ViewSets (jobs, manifests, callback)
│   │   ├── services.py                    #    OrchestratorDispatcher (HTTP dispatch)
│   │   ├── tasks.py                       #    Celery tasks (dispatch, stale check)
│   │   ├── urls.py                        #    DRF router
│   │   ├── admin.py                       #    Django admin
│   │   ├── management/commands/           #    seed_manifests command
│   │   └── tests/                         #    Unit + integration tests
│   ├── conftest.py                        # Shared test fixtures (DO NOT MODIFY)
│   └── manage.py
│
├── ai-brand-automator-frontend/           # Next.js 15 = frontend
│   └── src/
│       ├── components/pipelines/          # 🔄 THIS PLAN — ThoughtTrace, ResultDashboard
│       ├── app/dashboard/pipelines/       # 🔄 THIS PLAN — Pipeline pages
│       ├── types/orchestration.ts         # 🔄 THIS PLAN — TypeScript types
│       └── lib/orchestration-api.ts       # 🔄 THIS PLAN — API functions
│
├── deployment/                            # Docker Compose, Kong config
│   ├── config/kong/                       # gateway-service (Kong declarative config)
│   └── docker-compose.yml
│
├── pipeline-orchestrator-svc/             # ⬜ FUTURE — Separate top-level directory
│   └── (LangGraph + FastAPI, own requirements.txt)
│
├── discovery-agent-svc/                   # ⬜ FUTURE — Separate top-level directory
│   └── (Playwright + REST, own requirements.txt)
│
├── intelligence-agent-svc/                # ⬜ FUTURE — Separate top-level directory
│   └── (Pandas/LLM + REST, own requirements.txt)
│
└── docs/
    └── ORCHESTRATION_IMPLEMENTATION_PLAN.md
```

### HLD Service Name → Actual Path Mapping

| HLD Service Name | Actual Path | Structure | Reason |
|-----------------|-------------|-----------|--------|
| `gateway-service` | `deployment/config/kong/` | Kong YAML config | DB-less declarative config, no custom code |
| `core-api-service` | `ai-brand-automator/` (whole project) | Django project | Shares DB, Celery, auth, middleware with all apps |
| `core-api-service/orchestration` | `ai-brand-automator/orchestration/` | Django app | ★ This plan — new app inside existing project |
| `data-ingestion-svc` | `ai-brand-automator/data_ingestion/` | Django app (Hexagonal) | Shares Celery, DB (Hexagonal for domain logic) |
| `media-curation-svc` | `ai-brand-automator/media_curation/` | Django app (Hexagonal) | Shares Celery, Kafka consumer |
| `rag-index-svc` | `ai-brand-automator/rag_index/` | Django app (Hexagonal) | Shares Celery, Vertex AI config |
| `pipeline-orchestrator-svc` | `pipeline-orchestrator-svc/` ⬜ | **Separate directory** | Different stack: LangGraph + FastAPI + Redis |
| `discovery-agent-svc` | `discovery-agent-svc/` ⬜ | **Separate directory** | Different stack: Playwright + REST |
| `intelligence-agent-svc` | `intelligence-agent-svc/` ⬜ | **Separate directory** | Different stack: Pandas + LLM + REST |
| `frontend` | `ai-brand-automator-frontend/` | Next.js project | Existing frontend project |

### Why Hybrid (Option A)

- **Implemented services stay as Django apps**: `data_ingestion/`, `media_curation/`, `rag_index/` are deeply integrated — they share the Django ORM, Celery worker, `conftest.py` fixtures, and 1890+ existing tests. Extracting them would be a major migration with no immediate benefit.
- **New services get separate directories**: `pipeline-orchestrator-svc` (LangGraph/FastAPI), `discovery-agent-svc` (Playwright), and `intelligence-agent-svc` (Pandas) use fundamentally different stacks that don't fit inside a Django project.
- **Orchestration stays in the monolith**: It needs direct DB access to `PipelineManifest`, `AnalysisJob`, tenant models, and user auth — all of which are already in `ai-brand-automator/`.

---

## System Architecture Context

The AI Brand Automator platform is divided into **4 functional clusters**. The `core-api-service` (this app) acts as the **"Brain"** that connects the user to the **"Muscles"** (the external microservices).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SYSTEM ARCHITECTURE (HLD v6.0)                      │
│                                                                             │
│  ┌──────────────────────────────┐                                           │
│  │  1. INGRESS CLUSTER          │                                           │
│  │  (Implemented)               │                                           │
│  │  ┌────────────────────────┐  │                                           │
│  │  │  gateway-service       │  │  Kong: JWT auth, CORS, X-Tenant-ID        │
│  │  │  (Kong)                │  │  injection, rate limiting                  │
│  │  └──────────┬─────────────┘  │                                           │
│  └─────────────┼────────────────┘                                           │
│                │                                                            │
│  ┌─────────────▼────────────────┐  ┌────────────────────────────────────┐   │
│  │  2. COMMAND CENTER           │  │  3. DATA & KNOWLEDGE CLUSTER       │   │
│  │  (This Plan)                 │  │  (Implemented)                      │   │
│  │  ┌────────────────────────┐  │  │  ┌────────────────────────────┐    │   │
│  │  │  core-api-service  ★   │──┼──│  │  data-ingestion-svc        │    │   │
│  │  │  (Django/DRF)          │  │  │  │  media-curation-svc        │    │   │
│  │  │  - PipelineManifest    │  │  │  │  rag-index-svc             │    │   │
│  │  │  - AnalysisJob         │  │  │  │  → GCS + Vertex AI Search  │    │   │
│  │  │  - OrchestratorDispatch│  │  │  └────────────────────────────┘    │   │
│  │  └──────────┬─────────────┘  │  └────────────────────────────────────┘   │
│  └─────────────┼────────────────┘                                           │
│                │                                                            │
│  ┌─────────────▼────────────────┐  ┌────────────────────────────────────┐   │
│  │  4. EXECUTION ENGINE         │  │  5. AGENT ECOSYSTEM                │   │
│  │  (To Be Implemented)         │  │  (To Be Implemented)               │   │
│  │  ┌────────────────────────┐  │  │  ┌────────────────────────────┐    │   │
│  │  │  pipeline-orchestrator │──┼──│  │  discovery-agent-svc       │    │   │
│  │  │  (LangGraph)           │  │  │  │  (Playwright scraping)     │    │   │
│  │  │  - Dynamic Node Factory│  │  │  │                            │    │   │
│  │  │  - Intent Router       │  │  │  │  intelligence-agent-svc    │    │   │
│  │  │  - State Checkpoints   │  │  │  │  (ISO 10668 math/Pandas)   │    │   │
│  │  └────────────────────────┘  │  │  └────────────────────────────┘    │   │
│  └──────────────────────────────┘  └────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Inter-Service Request Flow

| Phase | Service | Action |
|-------|---------|--------|
| 1. Entry | `gateway-service` (Kong) | Validates JWT, injects `X-Tenant-ID`, proxies to backend |
| 2. Command | `core-api-service` (Django) ★ | Creates `AnalysisJob`, resolves tenant context, sends manifest to orchestrator |
| 3. Logic | `pipeline-orchestrator-svc` (LangGraph) | Builds the LangGraph from JSON manifest, manages state checkpoints |
| 4. Research | `discovery-agent-svc` (Playwright) | Scrapes external web data (market trends, competitor info) |
| 5. Analysis | `intelligence-agent-svc` (Pandas/LLM) | Performs ISO 10668 math, financial analysis, reasoning |
| 6. Context | `rag-index-svc` (Vertex AI) | Provides user's historical onboarding data via RAG |
| 7. Close | `core-api-service` (Django) ★ | Receives result callback and saves to DB |

### Why This Architecture

- **Decoupling**: Adding a new agent (e.g. "Legal Agent") only requires creating a new microservice and referencing its URL in a JSON manifest. No redeployment of the Orchestrator or Core API.
- **Scalability**: 1,000 scraping tasks only scales `discovery-agent-svc`. The core-api-service remains lightweight.
- **Tenant Security**: The core-api-service ensures the orchestrator only sees the tenant's `gcs_raw_bucket` for the specific `X-Tenant-ID` provided by Kong.

### Microservice Inventory

| HLD Service Name | Actual Path | Stack | Status | Role |
|-----------------|-------------|-------|--------|------|
| `gateway-service` | `deployment/config/kong/` | Kong | ✅ Implemented | Ingress Shield: JWT, CORS, tenant injection |
| `data-ingestion-svc` | `ai-brand-automator/data_ingestion/` | Python (Django app) | ✅ Implemented | File validation, Landing → Raw GCS moves |
| `media-curation-svc` | `ai-brand-automator/media_curation/` | Vertex AI/DLP (Django app) | ✅ Implemented | Binary → JSON Knowledge (STT, OCR, PII) |
| `rag-index-svc` | `ai-brand-automator/rag_index/` | Vertex Search (Django app) | ✅ Implemented | Indexes curated JSON into RAG Data Store |
| **`core-api-service`** | **`ai-brand-automator/orchestration/`** | **Django (DRF)** | **🔄 This Plan** | **Command Center: Job lifecycle, Manifest repo, RBAC** |
| `pipeline-orchestrator-svc` | `pipeline-orchestrator-svc/` ⬜ | LangGraph + FastAPI | ⬜ Next (separate dir) | Engine: Parses manifests, builds graphs, manages state |
| `discovery-agent-svc` | `discovery-agent-svc/` ⬜ | Playwright | ⬜ Future (separate dir) | Generic web scraper for research tasks |
| `intelligence-agent-svc` | `intelligence-agent-svc/` ⬜ | Pandas/LLM | ⬜ Future (separate dir) | Domain analyst for ISO math and reasoning |

---

## Data Model Design

### PipelineManifest

Defines a reusable pipeline template — what agents to invoke, in what order, with what configuration.

> **Schema Alignment (HLD v6.0)**: The `manifest_data` JSONB follows the "Pipeline-as-Code" format from the HLD, using **nodes** (not "agents") with `type: "internal"` or `type: "external"`. This allows the orchestrator's Dynamic Node Factory to construct the LangGraph at runtime.

```python
class PipelineManifest(models.Model):
    """
    A reusable pipeline definition (LangGraph-compatible).

    The manifest_data JSONB stores the full pipeline graph using
    the HLD v6.0 "Pipeline-as-Code" node format:
    {
        "pipeline_id": "iso-brand-equity-v1",
        "nodes": [
            {
                "id": "intent_router",
                "type": "internal",
                "handler": "RouterNode",
                "config": {}
            },
            {
                "id": "web_research",
                "type": "external",
                "url": "http://discovery-agent-svc/v1/search",
                "config": {"timeout": 60}
            },
            {
                "id": "valuation_logic",
                "type": "external",
                "url": "http://intelligence-agent-svc/v1/iso-calc",
                "config": {"method": "royalty_relief"}
            }
        ],
        "edges": [
            ["intent_router", "web_research"],
            ["web_research", "valuation_logic"]
        ],
        "global_config": {
            "model": "gemini-2.0-flash",
            "temperature": 0.7
        }
    }

    Node types:
    - "internal": Handled within the orchestrator (e.g., RouterNode, ManagerNode)
    - "external": REST call to a separate agent microservice (has "url" field)
    """
    pipeline_id = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Human-readable identifier (e.g., 'brand-analysis-v1')",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    manifest_data = models.JSONField(
        help_text="LangGraph-compatible pipeline definition (agents, edges, config)",
    )
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pipeline_manifests",
    )
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_manifests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["pipeline_id", "version"],
                name="unique_pipeline_version",
            ),
        ]

    def __str__(self):
        return f"{self.name} v{self.version} ({self.pipeline_id})"
```

### AnalysisJob

Tracks a single execution of a pipeline manifest.

```python
class AnalysisJob(models.Model):
    """
    Tracks a single pipeline execution.

    Lifecycle: QUEUED → RUNNING → COMPLETED / FAILED
    """
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    job_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="analysis_jobs",
    )
    manifest = models.ForeignKey(
        PipelineManifest,
        on_delete=models.PROTECT,
        null=True,          # Nullable: supports auto-detect/intent routing mode
        blank=True,         # When null, orchestrator selects manifest via intent routing
        related_name="jobs",
    )
    input_prompt = models.TextField(
        help_text="User's natural language analysis request",
    )
    input_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context (company_id, brand assets, etc.)",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    progress = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-agent progress: {'agent_id': {'status': 'done', 'output': {...}}}",
    )
    result_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Final aggregated results from the pipeline",
    )
    error_message = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analysis_jobs",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job {self.job_id} ({self.status})"

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
```

---

## API Endpoints

### AnalysisJob Endpoints

| Method | Path | Description | Permission |
|--------|------|-------------|------------|
| `POST` | `/api/v1/orchestration/jobs/` | Create + dispatch a new analysis job | `IsTenantEditor` |
| `GET` | `/api/v1/orchestration/jobs/` | List user's jobs (filtered by tenant) | `IsTenantViewer` |
| `GET` | `/api/v1/orchestration/jobs/{job_id}/` | Get job details + progress + results | `IsTenantViewer` |
| `PATCH` | `/api/v1/orchestration/jobs/{job_id}/callback/` | Callback from orchestrator (progress/results) | Service-to-service auth |
| `POST` | `/api/v1/orchestration/jobs/{job_id}/cancel/` | Cancel a running job | `IsTenantEditor` |

### PipelineManifest Endpoints

| Method | Path | Description | Permission |
|--------|------|-------------|------------|
| `GET` | `/api/v1/orchestration/manifests/` | List available manifests | `IsTenantViewer` |
| `GET` | `/api/v1/orchestration/manifests/{id}/` | Get manifest details | `IsTenantViewer` |
| `POST` | `/api/v1/orchestration/manifests/` | Create a new manifest | `IsTenantAdmin` |
| `PUT` | `/api/v1/orchestration/manifests/{id}/` | Update manifest (bumps version) | `IsTenantAdmin` |
| `DELETE` | `/api/v1/orchestration/manifests/{id}/` | Soft-delete (deactivate) manifest | `IsTenantAdmin` |

### Callback Authentication

The callback endpoint (`/callback/`) is called by the external `pipeline-orchestrator-svc`. It uses a shared secret token for authentication:

```python
# Callback authenticates via X-Callback-Token header
# Token is stored in env: ORCHESTRATOR_CALLBACK_TOKEN
# The callback endpoint verifies: request.META["HTTP_X_CALLBACK_TOKEN"] == settings.ORCHESTRATOR_CALLBACK_TOKEN
```

This is a service-to-service call that bypasses user authentication but still requires the callback token.

---

## Intent Routing & Default Pipeline

The HLD v6.0 defines an **Intent Router** inside the `pipeline-orchestrator-svc` that classifies user prompts and selects the appropriate pipeline. This impacts how the `core-api-service` dispatches jobs.

### How Intent Routing Works

```
User Prompt → core-api-service → pipeline-orchestrator-svc
                                        │
                                   Intent Router
                                        │
                        ┌───────────────┼───────────────┐
                        │               │               │
                  Specialized      Specialized     Default
                  Pipeline         Pipeline         General
                  (matched)        (matched)        Agent
                        │               │               │
                  ┌─────▼──────┐  ┌─────▼──────┐  ┌────▼─────┐
                  │ ISO Brand  │  │ Competitor │  │ RAG      │
                  │ Equity     │  │ Audit      │  │ Adapter  │
                  └────────────┘  └────────────┘  └──────────┘
```

### Scenarios

| Scenario | Manifest Selection | Pipeline Behavior |
|----------|-------------------|-------------------|
| **Explicit manifest** | User selects a manifest in the UI (manifest FK is set) | Orchestrator skips intent routing, builds graph from the provided manifest directly |
| **Auto-detect** | User submits prompt without selecting a manifest (manifest FK is null) | Orchestrator uses the Intent Router LLM node to classify the prompt and match to a manifest in its repository |
| **Default fallback** | No manifest matches the prompt intent | Orchestrator triggers the **Default General Agent**, which queries the RAG Adapter (Vertex AI Search) with the user's onboarded data |

### Impact on core-api-service

1. **`AnalysisJob.manifest` field becomes nullable**: When the user doesn't select a manifest, the job is created with `manifest=None`. The orchestrator resolves which pipeline to use.
2. **Dispatch payload includes all available manifests**: When `manifest` is null, the dispatcher sends the full manifest catalog so the orchestrator can pattern-match.
3. **Callback updates `manifest` FK**: When the orchestrator selects a manifest via intent routing, it reports back which manifest was used, and the core-api updates the job record.

> **Model Change Required**: `manifest = models.ForeignKey(PipelineManifest, ..., null=True, blank=True)` — already nullable in the current model design for this reason.

### Default General Agent (RAG Fallback)

When no specialized pipeline matches, the orchestrator creates a minimal 2-node graph:

```json
{
    "nodes": [
        {"id": "rag_query", "type": "internal", "handler": "RAGAdapterNode"},
        {"id": "synthesizer", "type": "internal", "handler": "SynthesizerNode"}
    ],
    "edges": [["rag_query", "synthesizer"]],
    "global_config": {"model": "gemini-2.0-flash"}
}
```

The **RAGAdapterNode** queries the Vertex AI Search data store containing the tenant's onboarded data (uploaded documents, company profiles, brand assets).

---

## Service Interaction Contracts

Precise HTTP contracts between `core-api-service` and `pipeline-orchestrator-svc`.

### Contract 1: Dispatch (core-api → orchestrator)

```
POST {ORCHESTRATOR_URL}/v1/jobs/dispatch
Headers:
    Content-Type: application/json
    X-Service-Token: {ORCHESTRATOR_SERVICE_TOKEN}  # Service-to-service auth

Request Body:
{
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "manifest": {                              # Full manifest object (or null for auto-detect)
        "pipeline_id": "iso-brand-equity-v1",
        "nodes": [...],
        "edges": [...],
        "global_config": {...}
    },
    "input_prompt": "Calculate Brand Equity using the uploaded 10-K",
    "input_context": {
        "company_id": 5,
        "company_name": "Acme Corp",
        "brand_assets": ["gs://tenant-123/raw/10k-2025.pdf"]
    },
    "tenant_context": {                        # Tenant-scoped data paths
        "tenant_id": "tenant-123",
        "gcs_raw_bucket": "brand-automator-raw/tenant-123/",
        "gcs_processed_bucket": "brand-automator-curated/tenant-123/",
        "rag_data_store_id": "projects/proj/locations/us/collections/default/dataStores/tenant-123"
    },
    "callback_url": "https://backend.railway.internal:8001/api/v1/orchestration/jobs/550e.../callback/",
    "available_manifests": [                   # Included when manifest is null (auto-detect)
        {"pipeline_id": "iso-brand-equity-v1", "name": "ISO Brand Equity", "description": "..."},
        {"pipeline_id": "competitor-audit", "name": "Competitor Audit", "description": "..."}
    ]
}

Response (202 Accepted):
{
    "status": "accepted",
    "job_id": "550e8400-e29b-41d4-a716-446655440000"
}

Response (400 Bad Request):
{
    "error": "Invalid manifest structure",
    "details": "Node 'web_research' has no 'url' for type 'external'"
}

Response (503 Service Unavailable):
{
    "error": "Orchestrator at capacity",
    "retry_after": 30
}
```

### Contract 2: Callback (orchestrator → core-api)

```
PATCH {callback_url}
Headers:
    Content-Type: application/json
    X-Callback-Token: {ORCHESTRATOR_CALLBACK_TOKEN}

Request Body (Progress Update):
{
    "status": "running",
    "progress": {
        "intent_router": {"status": "done", "output": {"selected_pipeline": "iso-brand-equity-v1"}},
        "web_research": {"status": "running", "started_at": "2026-02-17T10:00:12Z"}
    },
    "resolved_manifest_id": "iso-brand-equity-v1"   # Set when intent router picks a manifest
}

Request Body (Completion):
{
    "status": "completed",
    "progress": {
        "intent_router": {"status": "done"},
        "web_research": {"status": "done"},
        "valuation_logic": {"status": "done"}
    },
    "result_data": {
        "summary": "Brand Equity valued at $45.2M using Royalty Relief method",
        "sections": [
            {"title": "Market Overview", "content": "..."},
            {"title": "Brand Strength Index", "content": "BSI: 78/100"},
            {"title": "Valuation", "content": "NPV: $45.2M (5-year horizon)"}
        ],
        "raw_data": {"bsi": 78, "npv": 45200000, "royalty_rate": 0.035}
    }
}

Request Body (Failure):
{
    "status": "failed",
    "error_message": "Discovery agent timeout: unable to scrape royalty rate data",
    "progress": {
        "intent_router": {"status": "done"},
        "web_research": {"status": "failed", "error": "Timeout after 60s"}
    }
}

Response: {"status": "accepted"}
```

### Contract 3: Cancel (core-api → orchestrator)

```
POST {ORCHESTRATOR_URL}/v1/jobs/{job_id}/cancel
Headers:
    X-Service-Token: {ORCHESTRATOR_SERVICE_TOKEN}

Response (200):
{"status": "cancelled", "job_id": "550e..."}

Response (404):
{"error": "Job not found or already completed"}
```

---

## Service Layer: OrchestratorDispatcher

A service class that handles dispatching jobs to the external `pipeline-orchestrator-svc` via HTTP.

```python
class OrchestratorDispatcher:
    """
    Dispatches analysis jobs to the external pipeline-orchestrator-svc.

    The orchestrator is a separate Python/LangGraph microservice that:
    1. Receives a manifest (agent graph) + input prompt
    2. Executes agents in dependency order
    3. Calls back to our /callback/ endpoint with progress and results

    Configuration:
        ORCHESTRATOR_URL: Base URL of the pipeline-orchestrator-svc
        ORCHESTRATOR_CALLBACK_TOKEN: Shared secret for callback auth
        ORCHESTRATOR_TIMEOUT: HTTP timeout for dispatch call (seconds)
    """

    def __init__(self):
        from decouple import config
        self.orchestrator_url = config(
            "ORCHESTRATOR_URL", default="http://localhost:8010"
        )
        self.callback_token = config(
            "ORCHESTRATOR_CALLBACK_TOKEN", default="dev-callback-token"
        )
        self.timeout = config(
            "ORCHESTRATOR_TIMEOUT", default=30, cast=int
        )

    def dispatch(self, job):
        """
        POST the job to the orchestrator service.

        Payload (aligns with Service Interaction Contract 1):
        {
            "job_id": "uuid",
            "manifest": { ...node-based graph definition... } or null,
            "input_prompt": "Calculate Brand Equity using the 10-K...",
            "input_context": { "company_id": 5, "brand_assets": [...] },
            "tenant_context": {
                "tenant_id": "tenant-123",
                "gcs_raw_bucket": "brand-automator-raw/tenant-123/",
                "gcs_processed_bucket": "brand-automator-curated/tenant-123/",
                "rag_data_store_id": "projects/.../dataStores/tenant-123"
            },
            "callback_url": "https://api.example.com/api/v1/orchestration/jobs/{job_id}/callback/",
            "available_manifests": [...]  # When manifest is null (auto-detect mode)
        }

        The tenant_context ensures the orchestrator (and downstream agents)
        only access data belonging to the requesting tenant.

        Returns True on successful dispatch, False on failure.
        Updates job.status to RUNNING on success, FAILED on dispatch failure.
        """
        ...

    def _build_tenant_context(self, job):
        """
        Build tenant-scoped context for secure data isolation.

        Resolves the tenant's GCS bucket paths and RAG data store ID
        so the orchestrator only accesses the correct tenant's data.
        """
        tenant = job.tenant
        if not tenant:
            return {}
        return {
            "tenant_id": str(tenant.id),
            "gcs_raw_bucket": f"{settings.GS_BUCKET_NAME}/{tenant.id}/",
            "gcs_processed_bucket": f"{settings.GS_BUCKET_NAME}-curated/{tenant.id}/",
            "rag_data_store_id": getattr(tenant, "rag_data_store_id", ""),
        }

    def cancel(self, job):
        """
        POST cancel request to the orchestrator.
        """
        ...
```

**Key design decisions**:
- **Synchronous dispatch via HTTP** (not Kafka/Celery for the dispatch itself) — the orchestrator is a separate HTTP service
- **Async execution via Celery task** — `dispatch_job_task.delay(job_id)` wraps the HTTP call so the view returns immediately
- **Callback-based progress** — orchestrator POSTs to `/callback/` (not polling from orchestrator side)

---

## Celery Tasks

```python
# orchestration/tasks.py

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def dispatch_job_task(self, job_id):
    """
    Dispatch a job to the orchestrator service.
    Retries on connection errors.
    """
    job = AnalysisJob.objects.get(id=job_id)
    dispatcher = OrchestratorDispatcher()
    success = dispatcher.dispatch(job)
    if not success:
        raise self.retry(exc=Exception("Dispatch failed"))


@shared_task
def check_stale_jobs():
    """
    Periodic task: mark jobs as FAILED if RUNNING for > 30 minutes.
    Scheduled via CELERY_BEAT_SCHEDULE.
    """
    threshold = timezone.now() - timedelta(minutes=30)
    stale = AnalysisJob.objects.filter(
        status=AnalysisJob.Status.RUNNING,
        started_at__lt=threshold,
    )
    stale.update(
        status=AnalysisJob.Status.FAILED,
        error_message="Job timed out after 30 minutes",
        completed_at=timezone.now(),
    )
```

---

## ViewSet Design

### AnalysisJobViewSet

```python
class AnalysisJobViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    serializer_class = AnalysisJobSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "job_id"  # Use UUID in URLs, not integer PK
    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantEditor],
        "cancel": [IsAuthenticated, IsTenantEditor],
        "callback": [],  # Service-to-service auth handled in action
    }

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        qs = AnalysisJob.objects.select_related("manifest", "created_by")
        if tenant:
            qs = qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
        return qs

    def perform_create(self, serializer):
        tenant = getattr(self.request, "tenant", None)
        job = serializer.save(
            tenant=tenant,
            created_by=self.request.user,
            status=AnalysisJob.Status.QUEUED,
        )
        # Dispatch async via Celery
        dispatch_job_task.delay(job.id)

    @action(detail=True, methods=["patch"], url_path="callback")
    def callback(self, request, job_id=None):
        """
        Callback endpoint for pipeline-orchestrator-svc.
        Authenticates via X-Callback-Token header.
        Accepts progress updates and final results.
        """
        # Verify callback token
        token = request.META.get("HTTP_X_CALLBACK_TOKEN", "")
        if token != settings.ORCHESTRATOR_CALLBACK_TOKEN:
            return Response({"error": "Invalid callback token"}, status=403)

        job = self.get_object()
        # Update progress, status, result_data from request.data
        ...
        return Response({"status": "accepted"})

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, job_id=None):
        """Cancel a running job."""
        job = self.get_object()
        if job.status not in (AnalysisJob.Status.QUEUED, AnalysisJob.Status.RUNNING):
            return Response({"error": "Job cannot be cancelled"}, status=400)
        # Notify orchestrator + update local status
        ...
```

### PipelineManifestViewSet

```python
class PipelineManifestViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
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
        tenant = getattr(self.request, "tenant", None)
        qs = PipelineManifest.objects.filter(is_active=True)
        if tenant:
            qs = qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
        return qs

    def perform_create(self, serializer):
        tenant = getattr(self.request, "tenant", None)
        serializer.save(
            tenant=tenant,
            created_by=self.request.user,
        )

    def perform_destroy(self, instance):
        """Soft-delete: deactivate instead of deleting."""
        instance.is_active = False
        instance.save(update_fields=["is_active"])
```

---

## Serializers

```python
# orchestration/serializers.py

class PipelineManifestSerializer(ModelSerializer):
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True
    )

    class Meta:
        model = PipelineManifest
        fields = [
            "id", "pipeline_id", "name", "description",
            "manifest_data", "version", "is_active",
            "created_by_email", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "version", "created_by_email", "created_at", "updated_at"]

    def validate_manifest_data(self, value):
        """Validate manifest structure per HLD v6.0 Pipeline-as-Code format."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("manifest_data must be a JSON object")
        if "nodes" not in value:
            raise serializers.ValidationError("manifest_data must contain 'nodes' key")
        if "edges" not in value:
            raise serializers.ValidationError("manifest_data must contain 'edges' key")
        # Validate node structure
        for node in value["nodes"]:
            if "id" not in node or "type" not in node:
                raise serializers.ValidationError(
                    "Each node must have 'id' and 'type' fields"
                )
            if node["type"] == "external" and "url" not in node:
                raise serializers.ValidationError(
                    f"External node '{node['id']}' must have a 'url' field"
                )
            if node["type"] == "internal" and "handler" not in node:
                raise serializers.ValidationError(
                    f"Internal node '{node['id']}' must have a 'handler' field"
                )
        # Validate no circular dependencies
        self._validate_no_cycles(value)
        return value

    def _validate_no_cycles(self, manifest):
        """Topological sort to detect circular dependencies."""
        ...


class PipelineManifestListSerializer(ModelSerializer):
    """Lightweight serializer for list views (excludes manifest_data)."""
    class Meta:
        model = PipelineManifest
        fields = ["id", "pipeline_id", "name", "description", "version", "is_active", "updated_at"]


class AnalysisJobCreateSerializer(ModelSerializer):
    """Serializer for creating a new analysis job."""
    class Meta:
        model = AnalysisJob
        fields = ["manifest", "input_prompt", "input_context"]

    def validate_manifest(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Cannot use an inactive manifest")
        return value


class AnalysisJobSerializer(ModelSerializer):
    """Full job serializer with progress and results."""
    manifest_name = serializers.CharField(source="manifest.name", read_only=True)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True
    )
    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = AnalysisJob
        fields = [
            "id", "job_id", "manifest", "manifest_name",
            "input_prompt", "input_context",
            "status", "progress", "result_data", "error_message",
            "created_by_email", "duration_seconds",
            "started_at", "completed_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "job_id", "status", "progress", "result_data",
            "error_message", "started_at", "completed_at",
            "created_at", "updated_at",
        ]


class CallbackSerializer(serializers.Serializer):
    """Validates callback payload from orchestrator."""
    status = serializers.ChoiceField(
        choices=AnalysisJob.Status.choices,
        required=False,
    )
    progress = serializers.JSONField(required=False)
    result_data = serializers.JSONField(required=False)
    error_message = serializers.CharField(required=False, allow_blank=True)
    resolved_manifest_id = serializers.SlugField(
        required=False,
        help_text="Pipeline ID resolved by intent routing (when job had no explicit manifest)",
    )
```

---

## URL Configuration

```python
# orchestration/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"jobs", views.AnalysisJobViewSet, basename="analysis-job")
router.register(r"manifests", views.PipelineManifestViewSet, basename="pipeline-manifest")

urlpatterns = [
    path("", include(router.urls)),
]
```

**Registration in main urls.py**:
```python
# brand_automator/urls.py — inside api/v1/ include block
path("orchestration/", include("orchestration.urls")),
```

---

## Settings & Configuration

### New Settings

```python
# brand_automator/settings.py

# Add to SHARED_APPS (after "rag_index")
"orchestration",

# Orchestrator service configuration
ORCHESTRATOR_URL = config("ORCHESTRATOR_URL", default="http://localhost:8010")
ORCHESTRATOR_CALLBACK_TOKEN = config("ORCHESTRATOR_CALLBACK_TOKEN", default="dev-callback-token")
ORCHESTRATOR_TIMEOUT = config("ORCHESTRATOR_TIMEOUT", default=30, cast=int)
```

### Celery Updates

```python
# brand_automator/celery.py — add to task_routes
"orchestration.tasks.*": {"queue": "orchestration"},

# settings.py — add to CELERY_BEAT_SCHEDULE
"check-stale-orchestration-jobs": {
    "task": "orchestration.tasks.check_stale_jobs",
    "schedule": 300.0,  # Every 5 minutes
},
```

### New Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCHESTRATOR_URL` | `http://localhost:8010` | Base URL of pipeline-orchestrator-svc |
| `ORCHESTRATOR_SERVICE_TOKEN` | `dev-service-token` | Auth token for dispatch calls (core-api → orchestrator) |
| `ORCHESTRATOR_CALLBACK_TOKEN` | `dev-callback-token` | Auth token for callback calls (orchestrator → core-api) |
| `ORCHESTRATOR_TIMEOUT` | `30` | HTTP timeout (seconds) for dispatch calls |

---

## Frontend Components

### 1. Pipeline Jobs Page

**Route**: `/dashboard/pipelines/page.tsx`

Displays list of user's analysis jobs with status indicators.

```
┌──────────────────────────────────────────────────────────────┐
│ Analysis Pipelines                          [+ New Analysis] │
├──────────────────────────────────────────────────────────────┤
│ 🟢 Brand Analysis - Bransol        Completed   2 min ago    │
│ 🔵 Market Research - Widget Corp   Running     30s elapsed   │
│ 🟡 Content Strategy - Acme         Queued      Just now      │
│ 🔴 Competitor Analysis - TestCo    Failed      5 min ago     │
└──────────────────────────────────────────────────────────────┘
```

### 2. Job Detail Page

**Route**: `/dashboard/pipelines/[jobId]/page.tsx`

Combines ThoughtTrace (progress) and ResultDashboard (results).

### 3. ThoughtTrace Component

**File**: `src/components/pipelines/ThoughtTrace.tsx`

A progress stepper showing per-agent status — renders from `job.progress` JSON.

```
┌─────────────────────────────────────────────┐
│ Pipeline Progress                           │
├─────────────────────────────────────────────┤
│ ✅ Market Researcher      Done (12s)        │
│ ⏳ Content Strategist     Running...        │
│ ⬜ Report Generator       Waiting           │
│                                             │
│ [=============>          ] 66%              │
└─────────────────────────────────────────────┘
```

**Behavior**:
- Polls `GET /api/v1/orchestration/jobs/{id}/` every 3 seconds while status is `QUEUED` or `RUNNING`
- Stops polling when status becomes `COMPLETED` or `FAILED`
- Uses `useEffect` + `setInterval` with cleanup

### 4. ResultDashboard Component

**File**: `src/components/pipelines/ResultDashboard.tsx`

Renders the final `result_data` JSON as structured content — sections, charts, recommendations.

```
┌─────────────────────────────────────────────┐
│ Analysis Results                            │
├─────────────────────────────────────────────┤
│ ## Market Overview                          │
│ [Chart: Market Share]                       │
│                                             │
│ ## Key Findings                             │
│ • Finding 1...                              │
│ • Finding 2...                              │
│                                             │
│ ## Recommendations                          │
│ 1. Recommendation 1...                      │
│ 2. Recommendation 2...                      │
│                                             │
│ [📥 Export PDF]  [📋 Copy]                  │
└─────────────────────────────────────────────┘
```

### 5. New Analysis Modal

**File**: `src/components/pipelines/NewAnalysisModal.tsx`

Form for creating a new analysis job — select manifest, enter prompt.

```
┌─────────────────────────────────────────────┐
│ New Analysis                          [✕]   │
├─────────────────────────────────────────────┤
│ Pipeline:  [Brand Analysis v1      ▼]       │
│                                             │
│ Prompt:                                     │
│ ┌─────────────────────────────────────────┐ │
│ │ Analyze the market positioning of our   │ │
│ │ brand and identify growth areas...      │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ Additional Context (optional):              │
│ [Include company data ☑]                    │
│ [Include brand assets ☑]                    │
│                                             │
│                     [Cancel] [Run Analysis]  │
└─────────────────────────────────────────────┘
```

### 6. TypeScript Types

**File**: `src/types/orchestration.ts`

```typescript
interface PipelineManifest {
  id: number;
  pipeline_id: string;
  name: string;
  description: string;
  manifest_data: Record<string, unknown>;
  version: number;
  is_active: boolean;
  updated_at: string;
}

interface AnalysisJob {
  id: number;
  job_id: string;
  manifest: number;
  manifest_name: string;
  input_prompt: string;
  input_context: Record<string, unknown>;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: Record<string, AgentProgress>;
  result_data: Record<string, unknown> | null;
  error_message: string;
  duration_seconds: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

interface AgentProgress {
  status: 'pending' | 'running' | 'done' | 'failed';
  output?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
}
```

### 7. Frontend API Functions

```typescript
// In existing apiClient pattern
const orchestrationApi = {
  listJobs: () => apiClient.get('/orchestration/jobs/'),
  getJob: (jobId: string) => apiClient.get(`/orchestration/jobs/${jobId}/`),
  createJob: (data: { manifest: number; input_prompt: string; input_context?: Record<string, unknown> }) =>
    apiClient.post('/orchestration/jobs/', data),
  cancelJob: (jobId: string) => apiClient.post(`/orchestration/jobs/${jobId}/cancel/`, {}),
  listManifests: () => apiClient.get('/orchestration/manifests/'),
  getManifest: (id: number) => apiClient.get(`/orchestration/manifests/${id}/`),
};
```

### 8. Sidebar Navigation Update

Add "Pipelines" link to the dashboard sidebar (visible to all roles):

```
Dashboard
Companies
Brand Assets
AI Chat
Content Calendar
Social Profiles
Pipelines          ← NEW
Team (Admin+)
```

---

## Phase 6: Unit Testing (Backend)

Unit tests verify individual components in isolation — models, serializers, services, and tasks — with all external dependencies mocked.

### 6.1 Test File Structure

```
orchestration/tests/
├── __init__.py
├── conftest.py             # Orchestration-specific fixtures
├── test_models.py          # Model creation, constraints, properties
├── test_serializers.py     # Validation, manifest cycle detection
├── test_services.py        # OrchestratorDispatcher (mocked HTTP)
├── test_tasks.py           # Celery task dispatch, stale job cleanup
├── test_views.py           # API endpoints, RBAC enforcement
└── test_callback.py        # Callback endpoint, token auth
```

### 6.2 Fixtures (orchestration/tests/conftest.py)

Reuses global fixtures from `conftest.py` (`tenant`, `tenant2`, `user`, `api_client`, `authenticated_client_with_tenant`, `membership_owner`, `membership_editor`, `membership_viewer`) and adds orchestration-specific ones:

```python
import pytest
from orchestration.models import PipelineManifest, AnalysisJob


@pytest.fixture
def sample_manifest_data():
    """Valid HLD v6.0 Pipeline-as-Code manifest structure."""
    return {
        "nodes": [
            {"id": "researcher", "type": "internal", "handler": "ResearchNode", "config": {}},
            {"id": "strategist", "type": "internal", "handler": "StrategyNode", "config": {}},
        ],
        "edges": [["researcher", "strategist"]],
        "global_config": {"model": "gemini-2.0-flash"},
    }


@pytest.fixture
def external_agent_manifest_data():
    """Manifest with external agent nodes (discovery + intelligence services)."""
    return {
        "nodes": [
            {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
            {"id": "web_research", "type": "external", "url": "http://discovery-agent-svc/v1/search"},
            {"id": "valuation", "type": "external", "url": "http://intelligence-agent-svc/v1/iso-calc"},
        ],
        "edges": [["intent_router", "web_research"], ["web_research", "valuation"]],
        "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7},
    }


@pytest.fixture
def cyclic_manifest_data():
    """Manifest with circular dependency for validation testing."""
    return {
        "nodes": [
            {"id": "a", "type": "internal", "handler": "NodeA"},
            {"id": "b", "type": "internal", "handler": "NodeB"},
            {"id": "c", "type": "internal", "handler": "NodeC"},
        ],
        "edges": [["a", "b"], ["b", "c"], ["c", "a"]],
    }


@pytest.fixture
def pipeline_manifest(tenant, user, sample_manifest_data):
    """Active pipeline manifest assigned to tenant."""
    return PipelineManifest.objects.create(
        pipeline_id="test-pipeline",
        name="Test Pipeline",
        manifest_data=sample_manifest_data,
        tenant=tenant,
        created_by=user,
    )


@pytest.fixture
def inactive_manifest(tenant, user, sample_manifest_data):
    """Deactivated manifest for rejection testing."""
    return PipelineManifest.objects.create(
        pipeline_id="inactive-pipeline",
        name="Inactive Pipeline",
        manifest_data=sample_manifest_data,
        is_active=False,
        tenant=tenant,
        created_by=user,
    )


@pytest.fixture
def analysis_job(tenant, user, pipeline_manifest):
    """Queued analysis job for testing."""
    return AnalysisJob.objects.create(
        tenant=tenant,
        manifest=pipeline_manifest,
        input_prompt="Analyze brand positioning",
        created_by=user,
    )


@pytest.fixture
def completed_job(tenant, user, pipeline_manifest):
    """Completed analysis job with result data."""
    from django.utils import timezone
    now = timezone.now()
    return AnalysisJob.objects.create(
        tenant=tenant,
        manifest=pipeline_manifest,
        input_prompt="Analyze competitors",
        status=AnalysisJob.Status.COMPLETED,
        result_data={"summary": "Analysis complete", "findings": []},
        created_by=user,
        started_at=now - timezone.timedelta(minutes=5),
        completed_at=now,
    )


@pytest.fixture
def running_job(tenant, user, pipeline_manifest):
    """Running analysis job for cancel/timeout testing."""
    from django.utils import timezone
    return AnalysisJob.objects.create(
        tenant=tenant,
        manifest=pipeline_manifest,
        input_prompt="Market research",
        status=AnalysisJob.Status.RUNNING,
        created_by=user,
        started_at=timezone.now(),
    )


@pytest.fixture
def mock_orchestrator_dispatch():
    """Mock the OrchestratorDispatcher.dispatch method."""
    from unittest.mock import patch, MagicMock
    with patch("orchestration.services.OrchestratorDispatcher.dispatch") as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_requests_post():
    """Mock requests.post for OrchestratorDispatcher HTTP calls."""
    from unittest.mock import patch, MagicMock
    with patch("orchestration.services.requests.post") as mock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "accepted"}
        mock.return_value = mock_response
        yield mock
```

### 6.3 Model Unit Tests (test_models.py — 12 tests)

| # | Test | Description | Mocking |
|---|------|-------------|---------|
| 1 | `test_create_pipeline_manifest` | Create manifest with valid data, verify all fields persisted | None |
| 2 | `test_manifest_unique_pipeline_version` | `UniqueConstraint(pipeline_id, version)` → IntegrityError on duplicate | None |
| 3 | `test_manifest_slug_validation` | `pipeline_id` accepts valid slugs like `brand-analysis-v1` | None |
| 4 | `test_manifest_str_representation` | `__str__` returns `"Test Pipeline v1 (test-pipeline)"` | None |
| 5 | `test_manifest_default_version` | New manifest defaults to `version=1` | None |
| 6 | `test_manifest_ordering` | QuerySet ordered by `-updated_at` | None |
| 7 | `test_create_analysis_job` | Create job with all required fields, verify persistence | None |
| 8 | `test_job_uuid_auto_generated` | `job_id` is auto-populated UUID, unique, not editable | None |
| 9 | `test_job_default_status` | New job defaults to `Status.QUEUED` | None |
| 10 | `test_job_duration_seconds_completed` | Returns `(completed_at - started_at).total_seconds()` for completed job | None |
| 11 | `test_job_duration_seconds_null_when_incomplete` | Returns `None` when `completed_at` is null | None |
| 12 | `test_job_manifest_protect_delete` | Deleting manifest with linked jobs raises `ProtectedError` | None |

```python
# Example test implementation pattern
@pytest.mark.django_db
class TestPipelineManifest:
    def test_create_pipeline_manifest(self, pipeline_manifest):
        assert pipeline_manifest.pipeline_id == "test-pipeline"
        assert pipeline_manifest.name == "Test Pipeline"
        assert pipeline_manifest.version == 1
        assert pipeline_manifest.is_active is True
        assert "agents" in pipeline_manifest.manifest_data
        assert "edges" in pipeline_manifest.manifest_data

    def test_manifest_unique_pipeline_version(self, pipeline_manifest, tenant, user, sample_manifest_data):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            PipelineManifest.objects.create(
                pipeline_id="test-pipeline",  # Same as existing
                name="Duplicate",
                manifest_data=sample_manifest_data,
                version=1,  # Same version
                tenant=tenant,
                created_by=user,
            )

    def test_job_manifest_protect_delete(self, pipeline_manifest, analysis_job):
        from django.db.models import ProtectedError
        with pytest.raises(ProtectedError):
            pipeline_manifest.delete()


@pytest.mark.django_db
class TestAnalysisJob:
    def test_job_duration_seconds_completed(self, completed_job):
        assert completed_job.duration_seconds is not None
        assert completed_job.duration_seconds > 0

    def test_job_duration_seconds_null_when_incomplete(self, analysis_job):
        assert analysis_job.duration_seconds is None
```

### 6.4 Serializer Unit Tests (test_serializers.py — 12 tests)

| # | Test | Description | Mocking |
|---|------|-------------|---------|
| 1 | `test_manifest_serializer_valid` | Valid `manifest_data` with `nodes` + `edges` passes validation | None |
| 2 | `test_manifest_serializer_missing_nodes` | Rejects manifest without `nodes` key → `ValidationError` | None |
| 3 | `test_manifest_serializer_missing_edges` | Rejects manifest without `edges` key → `ValidationError` | None |
| 4 | `test_manifest_serializer_invalid_type` | `manifest_data` as string/list → `ValidationError` | None |
| 5 | `test_manifest_serializer_cycle_detection` | Rejects circular `A→B→C→A` dependencies → `ValidationError` | None |
| 6 | `test_manifest_serializer_read_only_fields` | `id`, `version`, `created_at`, `updated_at` are read-only | None |
| 7 | `test_manifest_list_serializer_excludes_data` | List serializer omits `manifest_data` field | None |
| 8 | `test_manifest_external_node_requires_url` | External node missing `url` → `ValidationError` | None |
| 9 | `test_manifest_internal_node_requires_handler` | Internal node missing `handler` → `ValidationError` | None |
| 10 | `test_job_create_serializer_valid` | Valid manifest FK + prompt passes | None |
| 11 | `test_job_create_serializer_null_manifest` | Null manifest (auto-detect mode) passes validation | None |
| 12 | `test_job_create_serializer_inactive_manifest` | Rejects reference to inactive manifest → `ValidationError` | None |
| 13 | `test_job_serializer_computed_fields` | `manifest_name`, `duration_seconds`, `created_by_email` populated | None |
| 14 | `test_callback_serializer_valid` | Accepts `status`, `progress`, `result_data` | None |
| 15 | `test_callback_serializer_partial_update` | Accepts only `progress` without `status` or `result_data` | None |
| 16 | `test_callback_serializer_resolved_manifest` | Accepts `resolved_manifest_id` for intent-routed jobs | None |

```python
# Example test implementation
@pytest.mark.django_db
class TestPipelineManifestSerializer:
    def test_manifest_serializer_cycle_detection(self, cyclic_manifest_data):
        from orchestration.serializers import PipelineManifestSerializer
        data = {
            "pipeline_id": "cyclic-test",
            "name": "Cyclic Pipeline",
            "manifest_data": cyclic_manifest_data,
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        assert "manifest_data" in serializer.errors

    def test_manifest_external_node_requires_url(self):
        from orchestration.serializers import PipelineManifestSerializer
        data = {
            "pipeline_id": "bad-external",
            "name": "Bad External Node",
            "manifest_data": {
                "nodes": [
                    {"id": "scraper", "type": "external"}  # Missing "url"
                ],
                "edges": [],
            },
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        assert "manifest_data" in serializer.errors

    def test_job_create_serializer_inactive_manifest(self, inactive_manifest):
        from orchestration.serializers import AnalysisJobCreateSerializer
        data = {
            "manifest": inactive_manifest.id,
            "input_prompt": "Test prompt",
        }
        serializer = AnalysisJobCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "manifest" in serializer.errors
```

### 6.5 Service Unit Tests (test_services.py — 9 tests)

All tests mock the `requests.post` call to the external orchestrator.

| # | Test | Description | Mocking |
|---|------|-------------|---------|
| 1 | `test_dispatch_success` | HTTP 202 → returns `True`, job status → `RUNNING` | `requests.post` |
| 2 | `test_dispatch_connection_error` | `ConnectionError` → returns `False`, job stays `QUEUED` | `requests.post` |
| 3 | `test_dispatch_timeout` | `Timeout` → returns `False`, job stays `QUEUED` | `requests.post` |
| 4 | `test_dispatch_http_500` | HTTP 500 → returns `False`, job status → `FAILED` | `requests.post` |
| 5 | `test_dispatch_payload_format` | Verifies JSON payload: `job_id`, `manifest`, `input_prompt`, `callback_url`, `tenant_context` | `requests.post` |
| 6 | `test_dispatch_includes_callback_url` | `callback_url` contains `/api/v1/orchestration/jobs/{job_id}/callback/` | `requests.post` |
| 7 | `test_dispatch_includes_tenant_context` | `tenant_context` contains `tenant_id`, `gcs_raw_bucket`, `gcs_processed_bucket` | `requests.post` |
| 8 | `test_dispatch_null_manifest_includes_available` | When `job.manifest` is null, payload includes `available_manifests` list | `requests.post` |
| 9 | `test_cancel_dispatch_success` | Cancel sends POST to orchestrator, returns True | `requests.post` |
| 10 | `test_dispatcher_config_from_env` | `ORCHESTRATOR_URL`, `_CALLBACK_TOKEN`, `_TIMEOUT` read from `decouple.config()` | `decouple.config` |
| 11 | `test_dispatch_sets_started_at` | On successful dispatch, `job.started_at` is set to current time | `requests.post` |
| 12 | `test_build_tenant_context_with_tenant` | Returns correct GCS paths and RAG store ID for tenant | None |
| 13 | `test_build_tenant_context_without_tenant` | Returns empty dict when job has no tenant | None |

```python
# Example test implementation
@pytest.mark.django_db
class TestOrchestratorDispatcher:
    def test_dispatch_success(self, analysis_job, mock_requests_post):
        from orchestration.services import OrchestratorDispatcher
        dispatcher = OrchestratorDispatcher()
        result = dispatcher.dispatch(analysis_job)
        assert result is True
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.RUNNING
        assert analysis_job.started_at is not None
        mock_requests_post.assert_called_once()

    def test_dispatch_payload_format(self, analysis_job, mock_requests_post):
        from orchestration.services import OrchestratorDispatcher
        dispatcher = OrchestratorDispatcher()
        dispatcher.dispatch(analysis_job)
        call_kwargs = mock_requests_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "job_id" in payload
        assert "manifest" in payload
        assert "input_prompt" in payload
        assert "callback_url" in payload
        assert str(analysis_job.job_id) in payload["callback_url"]
```

### 6.6 Celery Task Unit Tests (test_tasks.py — 7 tests)

| # | Test | Description | Mocking |
|---|------|-------------|---------|
| 1 | `test_dispatch_job_task_calls_dispatcher` | Task instantiates `OrchestratorDispatcher` and calls `dispatch(job)` | `OrchestratorDispatcher.dispatch` |
| 2 | `test_dispatch_job_task_retry_on_failure` | When dispatch returns `False`, task raises for retry | `OrchestratorDispatcher.dispatch` |
| 3 | `test_dispatch_job_task_nonexistent_job` | Task with invalid `job_id` raises `AnalysisJob.DoesNotExist` | None |
| 4 | `test_check_stale_jobs_marks_old_running` | Jobs RUNNING > 30 min → marked FAILED with timeout message | None |
| 5 | `test_check_stale_jobs_skips_recent_running` | Jobs RUNNING < 30 min → untouched | None |
| 6 | `test_check_stale_jobs_skips_completed` | COMPLETED jobs → untouched regardless of age | None |
| 7 | `test_check_stale_jobs_skips_queued` | QUEUED jobs → untouched (not yet dispatched) | None |

```python
# Example test implementation
@pytest.mark.django_db
class TestCheckStaleJobs:
    def test_check_stale_jobs_marks_old_running(self, running_job):
        from orchestration.tasks import check_stale_jobs
        from django.utils import timezone
        # Backdate started_at to 40 minutes ago
        running_job.started_at = timezone.now() - timezone.timedelta(minutes=40)
        running_job.save()

        check_stale_jobs()

        running_job.refresh_from_db()
        assert running_job.status == AnalysisJob.Status.FAILED
        assert "timed out" in running_job.error_message.lower()
        assert running_job.completed_at is not None

    def test_check_stale_jobs_skips_recent_running(self, running_job):
        from orchestration.tasks import check_stale_jobs
        # running_job.started_at is recent (just created)
        check_stale_jobs()
        running_job.refresh_from_db()
        assert running_job.status == AnalysisJob.Status.RUNNING
```

### 6.7 Frontend Unit Tests (Jest — 8 tests)

**File**: `src/components/pipelines/__tests__/`

| # | Test File | Test | Description |
|---|-----------|------|-------------|
| 1 | `ThoughtTrace.test.tsx` | `renders_progress_steps` | Renders agent steps from `job.progress` JSON |
| 2 | `ThoughtTrace.test.tsx` | `shows_running_indicator` | Running agent shows spinner/animation |
| 3 | `ThoughtTrace.test.tsx` | `shows_completed_checkmark` | Done agent shows checkmark |
| 4 | `ResultDashboard.test.tsx` | `renders_result_sections` | Renders sections from `result_data` |
| 5 | `ResultDashboard.test.tsx` | `shows_empty_state` | Shows placeholder when `result_data` is null |
| 6 | `NewAnalysisModal.test.tsx` | `submits_correct_payload` | Form sends `{manifest, input_prompt, input_context}` |
| 7 | `NewAnalysisModal.test.tsx` | `validates_required_fields` | Submit disabled when prompt is empty |
| 8 | `JobStatusBadge.test.tsx` | `renders_all_statuses` | Renders correct color/label for each status |

```tsx
// Example: ThoughtTrace.test.tsx
import { render, screen } from '@testing-library/react';
import ThoughtTrace from '../ThoughtTrace';

const mockProgress = {
  researcher: { status: 'done', completed_at: '2026-02-17T10:00:00Z' },
  strategist: { status: 'running', started_at: '2026-02-17T10:00:12Z' },
  reporter: { status: 'pending' },
};

describe('ThoughtTrace', () => {
  it('renders progress steps', () => {
    render(<ThoughtTrace progress={mockProgress} />);
    expect(screen.getByText(/researcher/i)).toBeInTheDocument();
    expect(screen.getByText(/strategist/i)).toBeInTheDocument();
    expect(screen.getByText(/reporter/i)).toBeInTheDocument();
  });

  it('shows running indicator for active agent', () => {
    render(<ThoughtTrace progress={mockProgress} />);
    // strategist should show running state
    const strategistEl = screen.getByText(/strategist/i).closest('[data-status]');
    expect(strategistEl?.getAttribute('data-status')).toBe('running');
  });
});
```

### 6.8 Running Unit Tests

```bash
# Backend unit tests
cd ai-brand-automator
pytest orchestration/tests/test_models.py -v
pytest orchestration/tests/test_serializers.py -v
pytest orchestration/tests/test_services.py -v
pytest orchestration/tests/test_tasks.py -v

# All orchestration tests together
pytest orchestration/tests/ -v

# With coverage
pytest orchestration/tests/ --cov=orchestration --cov-report=term-missing

# Frontend unit tests
cd ai-brand-automator-frontend
npm test -- --testPathPattern="pipelines"

# Format check (backend)
cd ai-brand-automator && black --check orchestration/ && flake8 orchestration/
```

### 6.9 Definition of Done — Unit Tests

- [ ] All 48 backend unit tests pass (`pytest orchestration/tests/ -v` = 0 failures)
- [ ] All 8 frontend unit tests pass (`npm test` = 0 failures)
- [ ] Backend coverage ≥ 85% for `orchestration/` app
- [ ] `black --check orchestration/` + `flake8 orchestration/` = 0 issues
- [ ] `npx tsc --noEmit` = 0 TypeScript errors
- [ ] No regressions: existing 1890+ backend tests still pass

---

## Phase 7: Integration Testing

Integration tests verify the full request/response cycle through the Django stack — middleware, authentication, RBAC, serialization, database writes — using DRF's `APIClient`.

### 7.1 Test File Structure

```
orchestration/tests/
├── test_views.py           # ViewSet integration tests (RBAC, CRUD, tenant isolation)
└── test_callback.py        # Callback endpoint (token auth, state transitions)
```

### 7.2 View Integration Tests — RBAC (test_views.py — 20 tests)

Each test authenticates as a specific role, sends a real HTTP request through middleware, and verifies the response status code and body.

**Setup Pattern**:
```python
@pytest.mark.django_db
class TestAnalysisJobViewSetRBAC:
    """Full request cycle through middleware → view → serializer → DB."""

    def _make_client(self, user, tenant, membership):
        """Create an authenticated APIClient with tenant context."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        client.force_authenticate(user=user)
        client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
        return client
```

#### Job Endpoints — RBAC Matrix

| # | Test | Role | Endpoint | Expected | Verifies |
|---|------|------|----------|----------|----------|
| 1 | `test_list_jobs_viewer` | VIEWER | `GET /api/v1/orchestration/jobs/` | 200 + job list | VIEWERs can read |
| 2 | `test_list_jobs_editor` | EDITOR | `GET /api/v1/orchestration/jobs/` | 200 | EDITORs can read |
| 3 | `test_list_jobs_unauthenticated` | None | `GET /api/v1/orchestration/jobs/` | 401 | Auth required |
| 4 | `test_create_job_editor` | EDITOR | `POST /api/v1/orchestration/jobs/` | 201 + job created in DB | EDITORs can create |
| 5 | `test_create_job_viewer_forbidden` | VIEWER | `POST /api/v1/orchestration/jobs/` | 403 | VIEWERs cannot create |
| 6 | `test_create_job_admin` | ADMIN | `POST /api/v1/orchestration/jobs/` | 201 | ADMINs can create |
| 7 | `test_retrieve_job_viewer` | VIEWER | `GET /api/v1/orchestration/jobs/{uuid}/` | 200 + full job data | VIEWERs can retrieve |
| 8 | `test_cancel_job_editor` | EDITOR | `POST /api/v1/orchestration/jobs/{uuid}/cancel/` | 200 + status → FAILED | EDITORs can cancel |
| 9 | `test_cancel_job_viewer_forbidden` | VIEWER | `POST /api/v1/orchestration/jobs/{uuid}/cancel/` | 403 | VIEWERs cannot cancel |
| 10 | `test_cancel_completed_job_fails` | EDITOR | `POST /api/v1/orchestration/jobs/{uuid}/cancel/` | 400 | Cannot cancel completed job |

#### Manifest Endpoints — RBAC Matrix

| # | Test | Role | Endpoint | Expected | Verifies |
|---|------|------|----------|----------|----------|
| 11 | `test_list_manifests_viewer` | VIEWER | `GET /api/v1/orchestration/manifests/` | 200 + manifest list | VIEWERs can read |
| 12 | `test_create_manifest_admin` | ADMIN | `POST /api/v1/orchestration/manifests/` | 201 + manifest in DB | ADMINs can create |
| 13 | `test_create_manifest_editor_forbidden` | EDITOR | `POST /api/v1/orchestration/manifests/` | 403 | EDITORs cannot create |
| 14 | `test_update_manifest_admin` | ADMIN | `PUT /api/v1/orchestration/manifests/{id}/` | 200 + fields updated | ADMINs can update |
| 15 | `test_update_manifest_editor_forbidden` | EDITOR | `PUT /api/v1/orchestration/manifests/{id}/` | 403 | EDITORs cannot update |
| 16 | `test_delete_manifest_admin_soft_deletes` | ADMIN | `DELETE /api/v1/orchestration/manifests/{id}/` | 204 + `is_active=False` | Soft-delete, not hard delete |
| 17 | `test_delete_manifest_editor_forbidden` | EDITOR | `DELETE /api/v1/orchestration/manifests/{id}/` | 403 | EDITORs cannot delete |

#### Tenant Isolation Tests

| # | Test | Description | Verifies |
|---|------|-------------|----------|
| 18 | `test_tenant_isolation_jobs` | User in Tenant A sends `X-Tenant-ID: B` (no membership) → 403 | Cross-tenant access blocked by middleware |
| 19 | `test_tenant_isolation_manifests` | Manifests from Tenant A not visible when querying as Tenant B | Data isolation via `Q(tenant=tenant)` filtering |
| 20 | `test_backward_compat_null_tenant_jobs` | Jobs with `tenant=NULL` (pre-tenant) visible via `Q(tenant__isnull=True)` | Backward compatibility |

```python
# Example integration test
@pytest.mark.django_db
class TestTenantIsolation:
    def test_tenant_isolation_jobs(
        self, tenant, tenant2, user, membership_owner, analysis_job
    ):
        """User in Tenant A cannot see jobs in Tenant B."""
        from rest_framework.test import APIClient
        from tenants.models import Membership
        from django.contrib.auth import get_user_model

        # Create a user in tenant2
        User = get_user_model()
        other_user = User.objects.create_user(
            username="other", email="other@test.com", password="testpass123!"
        )
        Membership.objects.create(
            user=other_user, tenant=tenant2, role=Membership.Role.OWNER
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        client.force_authenticate(user=other_user)
        client.defaults["HTTP_X_TENANT_ID"] = str(tenant2.id)

        response = client.get("/api/v1/orchestration/jobs/")
        assert response.status_code == 200
        # analysis_job belongs to tenant, not tenant2
        job_ids = [j["job_id"] for j in response.data["results"]]
        assert str(analysis_job.job_id) not in job_ids
```

### 7.3 Callback Integration Tests (test_callback.py — 10 tests)

Tests the callback endpoint's full lifecycle — from HTTP request through token verification to database state transitions.

| # | Test | Description | Verifies |
|---|------|-------------|----------|
| 1 | `test_callback_valid_token_progress_update` | Valid `X-Callback-Token` + progress JSON → 200, `job.progress` updated | Token auth + DB write |
| 2 | `test_callback_invalid_token` | Wrong token → 403, job unchanged | Security enforcement |
| 3 | `test_callback_missing_token` | No token header → 403 | Security enforcement |
| 4 | `test_callback_sets_status_running` | `{"status": "running"}` → `job.status=RUNNING`, `started_at` set | State transition |
| 5 | `test_callback_sets_status_completed` | `{"status": "completed", "result_data": {...}}` → stored, `completed_at` set | State transition + results |
| 6 | `test_callback_sets_status_failed` | `{"status": "failed", "error_message": "..."}` → stored | Error handling |
| 7 | `test_callback_partial_progress_merge` | Two sequential callbacks merge progress (don't overwrite) | Incremental updates |
| 8 | `test_callback_nonexistent_job` | Callback for invalid `job_id` → 404 | Edge case |
| 9 | `test_callback_completed_job_rejects_update` | Callback on already-completed job → 400 or ignored | Idempotency |
| 10 | `test_callback_sets_timestamps_correctly` | `started_at` on first RUNNING, `completed_at` on COMPLETED | Timestamp accuracy |
| 11 | `test_callback_resolved_manifest_updates_job` | `resolved_manifest_id` in callback → job's `manifest` FK updated | Intent routing resolution |
| 12 | `test_callback_resolved_manifest_nonexistent` | `resolved_manifest_id` for unknown pipeline → ignored gracefully | Robustness |

```python
# Example callback integration test
@pytest.mark.django_db
class TestCallbackEndpoint:
    def test_callback_valid_token_progress_update(self, api_client, analysis_job):
        """Full cycle: callback with valid token updates job progress."""
        from django.conf import settings

        url = f"/api/v1/orchestration/jobs/{analysis_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={
                "status": "running",
                "progress": {
                    "researcher": {"status": "running", "started_at": "2026-02-17T10:00:00Z"},
                },
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 200
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.RUNNING
        assert "researcher" in analysis_job.progress

    def test_callback_invalid_token(self, api_client, analysis_job):
        url = f"/api/v1/orchestration/jobs/{analysis_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={"status": "running"},
            format="json",
            HTTP_X_CALLBACK_TOKEN="wrong-token",
        )
        assert response.status_code == 403
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.QUEUED  # Unchanged
```

### 7.4 End-to-End Job Lifecycle Test (test_views.py — 3 tests)

These tests verify the complete lifecycle of a job through multiple API calls:

| # | Test | Flow | Verifies |
|---|------|------|----------|
| 1 | `test_full_job_lifecycle_happy_path` | Create job → callback RUNNING → callback progress → callback COMPLETED → retrieve results | Full workflow |
| 2 | `test_full_job_lifecycle_failure` | Create job → callback RUNNING → callback FAILED → retrieve error | Error workflow |
| 3 | `test_create_job_dispatches_celery_task` | Create job → verify `dispatch_job_task.delay(job.id)` called | Async dispatch |

```python
@pytest.mark.django_db
class TestJobLifecycle:
    def test_full_job_lifecycle_happy_path(
        self, api_client, user, tenant, membership_editor, pipeline_manifest
    ):
        """Complete lifecycle: create → running → progress → completed → retrieve."""
        from django.conf import settings
        from unittest.mock import patch

        # 1. Create job (as EDITOR)
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        client.force_authenticate(user=membership_editor.user)
        client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)

        with patch("orchestration.tasks.dispatch_job_task.delay"):
            response = client.post(
                "/api/v1/orchestration/jobs/",
                {"manifest": pipeline_manifest.id, "input_prompt": "Analyze brand"},
                format="json",
            )
        assert response.status_code == 201
        job_id = response.data["job_id"]

        # 2. Callback: RUNNING
        api_client.patch(
            f"/api/v1/orchestration/jobs/{job_id}/callback/",
            {"status": "running", "progress": {"researcher": {"status": "running"}}},
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )

        # 3. Callback: COMPLETED with results
        result_data = {"summary": "Brand is strong", "score": 85}
        api_client.patch(
            f"/api/v1/orchestration/jobs/{job_id}/callback/",
            {"status": "completed", "result_data": result_data},
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )

        # 4. Retrieve results (as VIEWER — should work)
        viewer_client = APIClient()
        viewer_client.defaults["SERVER_NAME"] = "localhost"
        viewer_client.force_authenticate(user=membership_editor.user)
        viewer_client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)

        response = viewer_client.get(f"/api/v1/orchestration/jobs/{job_id}/")
        assert response.status_code == 200
        assert response.data["status"] == "completed"
        assert response.data["result_data"]["score"] == 85
        assert response.data["duration_seconds"] is not None
```

### 7.5 Frontend Integration Tests (Jest — 5 tests)

| # | Test File | Test | Description |
|---|-----------|------|-------------|
| 1 | `PipelinesPage.test.tsx` | `renders_job_list_from_api` | Mocks `apiClient.get`, renders list with status badges |
| 2 | `PipelinesPage.test.tsx` | `navigates_to_job_detail` | Click on job row navigates to `/dashboard/pipelines/{id}` |
| 3 | `JobDetailPage.test.tsx` | `polls_and_updates_progress` | Mock polled responses, verify ThoughtTrace re-renders |
| 4 | `JobDetailPage.test.tsx` | `stops_polling_on_completed` | Verify `clearInterval` called when status = completed |
| 5 | `NewAnalysisModal.test.tsx` | `loads_manifests_and_submits` | Fetches manifest list, submits form, calls `createJob` API |

### 7.6 Running Integration Tests

```bash
# Backend integration tests (views + callback)
cd ai-brand-automator
pytest orchestration/tests/test_views.py -v
pytest orchestration/tests/test_callback.py -v

# All orchestration tests (unit + integration)
pytest orchestration/tests/ -v --tb=short

# Full backend regression (existing + new)
pytest -v

# Frontend integration tests
cd ai-brand-automator-frontend
npm test -- --testPathPattern="(PipelinesPage|JobDetailPage)"
```

### 7.7 Definition of Done — Integration Tests

- [ ] All 35 integration tests pass (20 RBAC + 12 callback + 3 lifecycle)
- [ ] All 5 frontend integration tests pass
- [ ] Tenant isolation: cross-tenant access returns 403 (verified in 2 tests)
- [ ] Backward compatibility: null-tenant data accessible (verified in 1 test)
- [ ] Full lifecycle test passes: create → running → completed → retrieve
- [ ] No regressions: `pytest -v` (full suite) = 0 failures
- [ ] ESLint: `npm run lint` = 0 errors

---

## Phase 8: Frontend Implementation

(Existing content — Types, API functions, ThoughtTrace, ResultDashboard, NewAnalysisModal, Pipeline pages, Sidebar update, Hydration safety guards)

---

## Phase 9: Deployment

### 9.1 Database Migration

```bash
# Generate migration for the new orchestration models
cd ai-brand-automator
python manage.py makemigrations orchestration

# Apply migration (shared schema — all tenants share the table)
python manage.py migrate_schemas --shared --noinput
```

**Migration file**: `orchestration/migrations/0001_initial.py`
- Creates `PipelineManifest` table with `unique_pipeline_version` constraint
- Creates `AnalysisJob` table with UUID index, status index, tenant FK
- Both tables use shared-schema FK filtering (not per-schema tables)

### 9.2 Seed Data — Default Manifests

**File**: `orchestration/management/commands/seed_manifests.py`

Management command to create the 3 built-in manifests (idempotent — skips if already exists):

```python
from django.core.management.base import BaseCommand
from orchestration.models import PipelineManifest


class Command(BaseCommand):
    help = "Seed default pipeline manifests"

    MANIFESTS = [
        {
            "pipeline_id": "iso-brand-equity",
            "name": "ISO Brand Equity Valuation",
            "description": (
                "ISO 10668-compliant brand equity valuation using Royalty Relief method. "
                "Requires financial data (10-K) and performs web research for market benchmarks."
            ),
            "manifest_data": {
                "nodes": [
                    {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
                    {
                        "id": "web_research",
                        "type": "external",
                        "url": "http://discovery-agent-svc/v1/search",
                        "config": {"focus": "royalty_rates,market_trends,brand_rankings"},
                    },
                    {
                        "id": "valuation_logic",
                        "type": "external",
                        "url": "http://intelligence-agent-svc/v1/iso-calc",
                        "config": {"method": "royalty_relief", "horizon_years": 5},
                    },
                    {"id": "manager", "type": "internal", "handler": "ManagerNode"},
                ],
                "edges": [
                    ["intent_router", "web_research"],
                    ["web_research", "valuation_logic"],
                    ["valuation_logic", "manager"],
                ],
                "global_config": {"model": "gemini-2.0-flash", "temperature": 0.3},
            },
        },
        {
            "pipeline_id": "brand-analysis",
            "name": "Brand Analysis",
            "description": "Analyze brand positioning, market fit, and growth opportunities",
            "manifest_data": {
                "nodes": [
                    {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": "http://discovery-agent-svc/v1/search",
                        "config": {"focus": "market_trends,competitors"},
                    },
                    {"id": "brand_strategist", "type": "internal", "handler": "StrategyNode"},
                    {"id": "report_generator", "type": "internal", "handler": "ReportNode"},
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "brand_strategist"],
                    ["brand_strategist", "report_generator"],
                ],
                "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7},
            },
        },
        {
            "pipeline_id": "competitor-audit",
            "name": "Competitor Audit",
            "description": "Identify competitors, analyze gaps, and recommend differentiation strategies",
            "manifest_data": {
                "nodes": [
                    {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
                    {
                        "id": "competitor_research",
                        "type": "external",
                        "url": "http://discovery-agent-svc/v1/search",
                        "config": {"focus": "competitors,market_share"},
                    },
                    {
                        "id": "gap_analyzer",
                        "type": "external",
                        "url": "http://intelligence-agent-svc/v1/analyze",
                        "config": {"analysis_type": "competitive_gap"},
                    },
                    {"id": "report_generator", "type": "internal", "handler": "ReportNode"},
                ],
                "edges": [
                    ["intent_router", "competitor_research"],
                    ["competitor_research", "gap_analyzer"],
                    ["gap_analyzer", "report_generator"],
                ],
                "global_config": {"model": "gemini-2.0-flash", "temperature": 0.5},
            },
        },
        {
            "pipeline_id": "content-strategy",
            "name": "Content Strategy",
            "description": "Generate content plans, audience analysis, and editorial calendars",
            "manifest_data": {
                "nodes": [
                    {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
                    {"id": "audience_analyzer", "type": "internal", "handler": "AudienceNode"},
                    {"id": "content_planner", "type": "internal", "handler": "PlannerNode"},
                    {"id": "calendar_builder", "type": "internal", "handler": "CalendarNode"},
                ],
                "edges": [
                    ["intent_router", "audience_analyzer"],
                    ["audience_analyzer", "content_planner"],
                    ["content_planner", "calendar_builder"],
                ],
                "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7},
            },
        },
    ]

    def handle(self, *args, **options):
        for manifest_data in self.MANIFESTS:
            obj, created = PipelineManifest.objects.get_or_create(
                pipeline_id=manifest_data["pipeline_id"],
                version=1,
                defaults={
                    "name": manifest_data["name"],
                    "description": manifest_data["description"],
                    "manifest_data": manifest_data["manifest_data"],
                    "tenant": None,  # Available to all tenants
                },
            )
            status = "Created" if created else "Already exists"
            self.stdout.write(f"  {status}: {obj.name}")
```

### 9.3 Environment Variables

Add to production `.env` (via Railway environment variables):

| Variable | Production Value | Description |
|----------|-----------------|-------------|
| `ORCHESTRATOR_URL` | `https://orchestrator.railway.internal:8010` | Internal Railway service URL |
| `ORCHESTRATOR_SERVICE_TOKEN` | `<generate-strong-secret>` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ORCHESTRATOR_CALLBACK_TOKEN` | `<generate-strong-secret>` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ORCHESTRATOR_TIMEOUT` | `30` | Dispatch HTTP timeout |

**Do NOT commit** secrets to `.env` files — use Railway's environment variable UI or `railway variables set`.

### 9.4 Celery Worker Configuration

Add the `orchestration` queue to the Celery worker startup command:

```bash
# Procfile (Railway) — update worker line
worker: celery -A brand_automator worker -l info -Q celery,orchestration,ingestion,curation

# Or as a separate dedicated worker for orchestration:
orchestration-worker: celery -A brand_automator worker -l info -Q orchestration -c 4
```

**Beat schedule**: The `check-stale-orchestration-jobs` task is automatically registered via `CELERY_BEAT_SCHEDULE` in settings.py — no additional deployment config needed.

### 9.5 Docker Configuration

**Update `Dockerfile`** — no changes needed (Django auto-discovers the `orchestration` app via `SHARED_APPS`).

**Update `docker-compose.yml`** — add environment variables:

```yaml
# ai-brand-automator/docker-compose.yml — backend service
services:
  backend:
    environment:
      - ORCHESTRATOR_URL=${ORCHESTRATOR_URL:-http://localhost:8010}
      - ORCHESTRATOR_SERVICE_TOKEN=${ORCHESTRATOR_SERVICE_TOKEN:-dev-service-token}
      - ORCHESTRATOR_CALLBACK_TOKEN=${ORCHESTRATOR_CALLBACK_TOKEN:-dev-callback-token}
      - ORCHESTRATOR_TIMEOUT=${ORCHESTRATOR_TIMEOUT:-30}
```

### 9.6 Railway Deployment

**File**: `ai-brand-automator/railway.json` — no changes needed (uses `start.sh` which runs `migrate_schemas` + `gunicorn`).

**Update `start.sh`** to include seed data:

```bash
#!/bin/bash
set -e

# Existing migration
python manage.py migrate_schemas --shared --noinput

# Seed default manifests (idempotent)
python manage.py seed_manifests

# Start server
exec gunicorn brand_automator.wsgi:application ...
```

### 9.7 Kong Gateway

**No changes needed.** The existing `/api/v1/*` catch-all route in Kong already forwards to the Django backend. New endpoints at `/api/v1/orchestration/*` are automatically covered.

The callback endpoint (`/api/v1/orchestration/jobs/{id}/callback/`) should be called **directly to the backend** (port 8001), bypassing Kong. This is a service-to-service call from the orchestrator — it doesn't need JWT authentication (uses `X-Callback-Token` instead).

If the orchestrator runs on Railway's internal network, the callback URL will be:
```
https://backend.railway.internal:8001/api/v1/orchestration/jobs/{job_id}/callback/
```

### 9.8 Frontend Build & Deploy

```bash
cd ai-brand-automator-frontend

# Verify build succeeds
npm run build

# No environment variable changes needed — 
# frontend uses existing NEXT_PUBLIC_API_URL and apiClient
# which already handles X-Tenant-ID injection
```

**Railway**: Frontend auto-deploys on push to `main` — no config changes needed.

### 9.9 Rollback Plan

| Component | Rollback Strategy |
|-----------|------------------|
| Database migration | `python manage.py migrate orchestration zero` drops both tables |
| SHARED_APPS entry | Remove `"orchestration"` from settings.py — app is ignored |
| URL routing | Remove `path("orchestration/", ...)` from urls.py — 404 on requests |
| Celery routing | Remove `"orchestration.tasks.*"` from task_routes — tasks go to default queue |
| Frontend pages | Remove `/dashboard/pipelines/` route — page shows 404 |
| Seed data | `PipelineManifest.objects.filter(tenant__isnull=True).delete()` |

All changes are additive — no existing tables, models, or endpoints are modified. Rollback is safe and does not affect other apps.

### 9.10 Deployment Checklist

```
Pre-deployment:
  [ ] All tests pass: pytest -v (backend), npm test (frontend)
  [ ] Formatting clean: black --check . && flake8 .
  [ ] TypeScript compiles: npx tsc --noEmit
  [ ] Feature branch merged to main via PR
  [ ] Environment variables set in Railway:
      - ORCHESTRATOR_URL
      - ORCHESTRATOR_SERVICE_TOKEN
      - ORCHESTRATOR_CALLBACK_TOKEN
      - ORCHESTRATOR_TIMEOUT

Deploy:
  [ ] Push to main → CI/CD triggers
  [ ] Railway runs start.sh:
      - migrate_schemas --shared --noinput (creates tables)
      - seed_manifests (creates default pipelines)
      - gunicorn starts
  [ ] Frontend auto-builds and deploys

Post-deployment verification:
  [ ] GET /api/v1/orchestration/manifests/ → 200 with 4 default manifests (including ISO Brand Equity)
  [ ] GET /api/v1/orchestration/jobs/ → 200 with empty list
  [ ] POST /api/v1/orchestration/jobs/ with valid data → 201
  [ ] Frontend /dashboard/pipelines renders correctly
  [ ] Celery worker processes orchestration queue
  [ ] Beat scheduler runs check_stale_jobs every 5 minutes
```

### 9.11 Monitoring & Observability

| What | How | Alert |
|------|-----|-------|
| Stale jobs | `check_stale_jobs` periodic task logs warnings | Log monitor for `"Job timed out"` |
| Dispatch failures | `OrchestratorDispatcher` logs errors on HTTP failures | Log monitor for `"Dispatch failed"` |
| Callback errors | Callback endpoint returns 4xx/5xx | HTTP error rate monitor |
| Queue depth | Celery `orchestration` queue length | Alert if > 50 pending tasks |
| Job completion rate | `AnalysisJob.objects.filter(status="completed").count()` | Dashboard metric |

---

## File-by-File Implementation Checklist

### New Backend Files (20 files — all inside `ai-brand-automator/orchestration/`)

| # | File | Description |
|---|------|-------------|
| 1 | `ai-brand-automator/orchestration/__init__.py` | Empty ✅ Created |
| 2 | `ai-brand-automator/orchestration/apps.py` | Django AppConfig ✅ Created |
| 3 | `ai-brand-automator/orchestration/models.py` | PipelineManifest + AnalysisJob ✅ Created |
| 4 | `ai-brand-automator/orchestration/serializers.py` | 5 serializers (manifests + jobs + callback) |
| 5 | `ai-brand-automator/orchestration/views.py` | 2 ViewSets (AnalysisJob + PipelineManifest) |
| 6 | `ai-brand-automator/orchestration/urls.py` | Router registration ✅ Created (placeholder) |
| 7 | `ai-brand-automator/orchestration/services.py` | OrchestratorDispatcher |
| 8 | `ai-brand-automator/orchestration/tasks.py` | Celery tasks (dispatch + stale check) |
| 9 | `ai-brand-automator/orchestration/admin.py` | Admin registration ✅ Created |
| 10 | `ai-brand-automator/orchestration/tests/__init__.py` | Empty |
| 11 | `ai-brand-automator/orchestration/tests/conftest.py` | Fixtures (manifest, job) |
| 12 | `ai-brand-automator/orchestration/tests/test_models.py` | 12 model tests |
| 13 | `ai-brand-automator/orchestration/tests/test_serializers.py` | 16 serializer tests |
| 14 | `ai-brand-automator/orchestration/tests/test_views.py` | 23 view integration tests (RBAC + lifecycle) |
| 15 | `ai-brand-automator/orchestration/tests/test_callback.py` | 12 callback integration tests |
| 16 | `ai-brand-automator/orchestration/tests/test_services.py` | 13 service unit tests |
| 17 | `ai-brand-automator/orchestration/tests/test_tasks.py` | 7 task unit tests |
| 18 | `ai-brand-automator/orchestration/management/__init__.py` | Empty |
| 19 | `ai-brand-automator/orchestration/management/commands/__init__.py` | Empty |
| 20 | `ai-brand-automator/orchestration/management/commands/seed_manifests.py` | Seed default manifests |

### Modified Backend Files (5 files — inside `ai-brand-automator/`)

| # | File | Change | Status |
|---|------|--------|--------|
| 1 | `ai-brand-automator/brand_automator/settings.py` | Add `"orchestration"` to SHARED_APPS, add orchestrator env vars, add beat schedule | ✅ Done |
| 2 | `ai-brand-automator/brand_automator/urls.py` | Add `path("orchestration/", include("orchestration.urls"))` | ✅ Done |
| 3 | `ai-brand-automator/brand_automator/celery.py` | Add `"orchestration.tasks.*": {"queue": "orchestration"}` to task_routes | ✅ Done |
| 4 | `ai-brand-automator/start.sh` | Add `python manage.py seed_manifests` after migrations | |
| 5 | `ai-brand-automator/docker-compose.yml` | Add `ORCHESTRATOR_*` environment variables to backend service | |

### Frontend New Files (12 files — inside `ai-brand-automator-frontend/`)

| # | File | Description |
|---|------|-------------|
| 1 | `src/types/orchestration.ts` | TypeScript interfaces |
| 2 | `src/lib/orchestration-api.ts` | API functions for orchestration endpoints |
| 3 | `src/app/dashboard/pipelines/page.tsx` | Job list page |
| 4 | `src/app/dashboard/pipelines/[jobId]/page.tsx` | Job detail page |
| 5 | `src/components/pipelines/ThoughtTrace.tsx` | Progress stepper component |
| 6 | `src/components/pipelines/ResultDashboard.tsx` | Results display component |
| 7 | `src/components/pipelines/NewAnalysisModal.tsx` | Job creation form |
| 8 | `src/components/pipelines/JobStatusBadge.tsx` | Status indicator component |
| 9 | `src/components/pipelines/__tests__/ThoughtTrace.test.tsx` | ThoughtTrace unit tests |
| 10 | `src/components/pipelines/__tests__/ResultDashboard.test.tsx` | ResultDashboard unit tests |
| 11 | `src/components/pipelines/__tests__/NewAnalysisModal.test.tsx` | NewAnalysisModal unit tests |
| 12 | `src/components/pipelines/__tests__/JobStatusBadge.test.tsx` | JobStatusBadge unit tests |

### Frontend Modified Files (1 file — inside `ai-brand-automator-frontend/`)

| # | File | Change |
|---|------|--------|
| 1 | Sidebar component | Add "Pipelines" navigation link |

---

## Phased Execution Order

```
Phase 1: Backend Foundation (Models + Migrations)
    │   - orchestration app scaffolding
    │   - PipelineManifest + AnalysisJob models
    │   - Migration
    │   - Admin registration
    │   - Settings: SHARED_APPS + env vars
    │
    ▼
Phase 2: Serializers + Validation (HLD v6.0 aligned)
    │   - All 5 serializers
    │   - Manifest validation (node structure + type + cycle detection)
    │   - External node URL validation
    │   - Internal node handler validation
    │   - Job creation validation (nullable manifest for auto-detect)
    │
    ▼
Phase 3: Views + URLs
    │   - PipelineManifestViewSet
    │   - AnalysisJobViewSet (without dispatch)
    │   - URL routing
    │   - RBAC enforcement
    │
    ▼
Phase 4: Service Layer + Celery
    │   - OrchestratorDispatcher (with tenant_context + service token)
    │   - dispatch_job_task
    │   - check_stale_jobs
    │   - Celery route + beat schedule
    │   - Wire perform_create → task dispatch
    │   - _build_tenant_context() method
    │
    ▼
Phase 5: Callback Endpoint
    │   - Callback action on AnalysisJobViewSet
    │   - Token authentication
    │   - Progress + result update logic
    │   - resolved_manifest_id handling (intent routing)
    │   - Progress merge (incremental, not overwrite)
    │
    ▼
Phase 6: Unit Testing (Backend + Frontend)
    │   - 12 model tests
    │   - 16 serializer tests (incl. node type validation)
    │   - 13 service tests (incl. tenant context, auto-detect)
    │   - 7 task tests (mocked dispatcher)
    │   - 8 frontend component tests (Jest)
    │   - black + flake8
    │   - Coverage ≥ 85%
    │
    ▼
Phase 7: Integration Testing
    │   - 20 RBAC view tests (role × endpoint matrix)
    │   - 12 callback integration tests (incl. intent routing)
    │   - 3 end-to-end lifecycle tests
    │   - 5 frontend integration tests
    │   - Tenant isolation verification
    │   - Full regression suite
    │
    ▼
Phase 8: Frontend Implementation
    │   - Types + API functions
    │   - ThoughtTrace + ResultDashboard components
    │   - NewAnalysisModal
    │   - Pipeline pages (list + detail)
    │   - Sidebar update
    │   - Hydration safety guards
    │
    ▼
Phase 9: Deployment
    │   - Database migration (migrate_schemas --shared)
    │   - Seed default manifests (management command)
    │   - Environment variables (Railway)
    │   - Celery worker + beat configuration
    │   - Docker compose update
    │   - start.sh update
    │   - Post-deployment verification
    │   - Monitoring setup
```

---

## Cross-Service Security Model

Security spans across all 4 clusters. The core-api-service enforces tenant isolation at every boundary.

### Authentication Flows

```
 User → Kong                    : JWT (Bearer token)
 Kong → core-api-service        : X-Tenant-ID, X-Kong-Proxy headers
 core-api → orchestrator        : X-Service-Token (shared secret)
 orchestrator → core-api        : X-Callback-Token (shared secret)
 orchestrator → agent services  : X-Service-Token (shared secret, different per service)
```

### Token Inventory

| Token | Direction | Env Variable | Purpose |
|-------|-----------|-------------|---------|
| JWT | User → Kong | N/A (per-user) | User authentication |
| `X-Service-Token` | core-api → orchestrator | `ORCHESTRATOR_SERVICE_TOKEN` | Dispatch auth |
| `X-Callback-Token` | orchestrator → core-api | `ORCHESTRATOR_CALLBACK_TOKEN` | Callback auth |
| `X-Agent-Token` | orchestrator → agents | `AGENT_SERVICE_TOKEN` | Agent call auth |

### Tenant Data Isolation Across Services

| Service | Isolation Mechanism |
|---------|-------------------|
| **core-api** | `Q(tenant=tenant)` DB filter on all queries |
| **orchestrator** | Receives `tenant_context.tenant_id` in dispatch — scopes all agent calls |
| **discovery-agent** | Receives `tenant_id` parameter — logs scoped to tenant |
| **intelligence-agent** | Receives `tenant_context.gcs_raw_bucket` — only reads tenant's files |
| **RAG (Vertex AI)** | Queries scoped to tenant's data store via `rag_data_store_id` |
| **GCS** | Paths prefixed with `{tenant_id}/` — agent services cannot access other tenant paths |

### Settings Update Required

```python
# Additional env var (beyond what's already in the plan)
ORCHESTRATOR_SERVICE_TOKEN = config(
    "ORCHESTRATOR_SERVICE_TOKEN", default="dev-service-token"
)
```

---

## End-to-End Flow: ISO Brand Equity Valuation

The flagship use case demonstrating the full 7-phase flow across all services.

### Scenario

User uploads a 10-K financial statement and asks: *"Calculate Brand Equity using the 10-K."*

### Phase-by-Phase Flow

```
Phase 1: Ingress (Already implemented)
    User uploads 10-K via /ingest/upload
    Kong validates JWT, injects X-Tenant-ID
    └── Request proxied to data-ingestion-svc

Phase 2: Data Processing (Already implemented)
    data-ingestion-svc → validates file, moves to GCS raw bucket
    media-curation-svc → extracts text from PDF (OCR), structures as JSON
    rag-index-svc → indexes structured JSON into Vertex AI Search
    └── 10-K is now searchable knowledge in the tenant's RAG store

Phase 3: Prompt Submission (This Plan — core-api-service)
    User sends: POST /api/v1/orchestration/jobs/
    {
      "manifest": <iso-brand-equity manifest ID>,    // or null for auto-detect
      "input_prompt": "Calculate Brand Equity using the 10-K",
      "input_context": {"company_id": 5}
    }
    core-api-service:
      ├── Creates AnalysisJob (status: QUEUED)
      ├── Resolves tenant GCS paths + RAG store ID
      └── Dispatches to orchestrator via Celery task

Phase 4: Pipeline Execution (To be implemented — pipeline-orchestrator-svc)
    Orchestrator receives dispatch:
      ├── Reads iso-brand-equity manifest
      ├── Builds LangGraph: intent_router → web_research → valuation_logic → manager
      └── Executes nodes in order:

    Node 1: Intent Router (internal)
      └── Classifies prompt → confirms "iso-brand-equity" pipeline

    Node 2: Web Research (external → discovery-agent-svc)
      ├── POST http://discovery-agent-svc/v1/search
      ├── Scrapes: industry royalty rates, current market trends, brand rankings
      └── Returns: {"royalty_rate_range": [0.02, 0.05], "market_cap": ...}

    Node 3: Valuation Logic (external → intelligence-agent-svc)
      ├── POST http://intelligence-agent-svc/v1/iso-calc
      ├── Fetches 10-K data from GCS via tenant_context.gcs_raw_bucket
      ├── Applies ISO 10668 Royalty Relief method:
      │     Revenue Forecasts × Royalty Rate × Brand Strength Index
      │     → Discounted Cash Flow → NPV
      └── Returns: {"bsi": 78, "npv": 45200000, "royalty_rate": 0.035}

    Node 4: Manager (internal)
      └── Synthesizes findings into structured report

    Callbacks throughout: PATCH /callback/ with progress updates

Phase 5: Result Delivery (This Plan — core-api-service)
    Final callback:
      ├── status: "completed"
      ├── result_data: {summary, sections, raw_data}
      └── core-api updates AnalysisJob, sets completed_at

    Frontend polls GET /api/v1/orchestration/jobs/{id}/
      ├── ThoughtTrace shows agent progress
      └── ResultDashboard renders final report with BSI and NPV
```

---

## Future Services Implementation Roadmap

The core-api-service is designed to work independently of downstream services. Implementation proceeds in 3 phases using the **hybrid structure** (Option A):

```
                Now                          Next                         Later
    ┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
    │  Phase 1 (This Plan)     │  │  Phase 2                 │  │  Phase 3                 │
    │                          │  │                          │  │                          │
    │  ai-brand-automator/     │  │  pipeline-orchestrator-  │  │  discovery-agent-svc/    │
    │    orchestration/        │  │  svc/  ← NEW TOP-LEVEL   │  │  ← NEW TOP-LEVEL DIR    │
    │  (Django app in monolith)│  │  (LangGraph + FastAPI)   │  │  (Playwright + REST)     │
    │                          │  │                          │  │                          │
    │  - Models                │  │  - Dynamic Node Factory  │  │  intelligence-agent-svc/ │
    │  - API endpoints         │  │  - Intent Router         │  │  ← NEW TOP-LEVEL DIR    │
    │  - Dispatch service      │  │  - State Checkpoints     │  │  (Pandas/LLM + REST)     │
    │  - Callback handler      │  │  - Redis persistence     │  │                          │
    │  - Manifest CRUD         │  │  - RAG Adapter Node      │  │  - ISO 10668 math        │
    │  - RBAC + Tenant         │  │                          │  │  - Web scraping          │
    │  - Frontend UI           │  │  Own: requirements.txt,  │  │  - Trend analysis        │
    │                          │  │  Dockerfile, main.py     │  │                          │
    │  Shares: DB, Celery,     │  │                          │  │  Own: requirements.txt,  │
    │  auth, middleware        │  │                          │  │  Dockerfile, main.py     │
    └──────────────────────────┘  └──────────────────────────┘  └──────────────────────────┘
           ★ NOW                       HIGH PRIORITY                MEDIUM PRIORITY
        (Django app inside              (Separate directory)        (Separate directories)
         ai-brand-automator/)
```

### Future Directory Layout (After All Phases)

```
Prevision_WS/
├── ai-brand-automator/                    # Django monolith (core-api + data cluster)
│   ├── orchestration/                     # ★ Phase 1 (this plan)
│   ├── data_ingestion/                    # ✅ Implemented
│   ├── media_curation/                    # ✅ Implemented
│   ├── rag_index/                         # ✅ Implemented
│   └── ...                                # All other Django apps
│
├── ai-brand-automator-frontend/           # Next.js frontend
│
├── pipeline-orchestrator-svc/             # ⬜ Phase 2 — LangGraph + FastAPI
│   ├── app/
│   │   ├── factory/graph_builder.py       #    JSON Manifest → LangGraph
│   │   ├── nodes/
│   │   │   ├── router_node.py             #    Intent classification
│   │   │   ├── external_node.py           #    Generic wrapper for agent services
│   │   │   └── default_agent.py           #    General Chat / RAG node
│   │   ├── state/schema.py                #    LangGraph TypedDict State
│   │   └── main.py                        #    FastAPI entry point
│   ├── redis_checkpointer/                #    State persistence
│   ├── Dockerfile
│   └── requirements.txt
│
├── discovery-agent-svc/                   # ⬜ Phase 3 — Playwright + REST
│   ├── scrapers/playwright_engine.py
│   ├── api/                               #    REST interface for orchestrator
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── intelligence-agent-svc/                # ⬜ Phase 3 — Pandas/LLM + REST
│   ├── logic/
│   │   ├── iso_10668_engine.py            #    Royalty Relief math
│   │   └── sentiment_analyzer.py          #    NLP themes
│   ├── api/                               #    REST interface for orchestrator
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── deployment/
│   ├── config/kong/                       # gateway-service config
│   └── docker-compose.yml                 # Orchestrates all services locally
│
└── docs/
```

### Phase 1 → Phase 2 Integration Contract

When `pipeline-orchestrator-svc/` is created as a **new top-level directory**:
1. It receives dispatch payloads from core-api-service (Contract 1 above)
2. It sends callbacks to core-api-service (Contract 2 above)
3. **No changes needed in `ai-brand-automator/`** — the `OrchestratorDispatcher` already sends the correct payload format
4. A new `Dockerfile` and `requirements.txt` will be created under `pipeline-orchestrator-svc/`
5. `deployment/docker-compose.yml` will be updated to include the new service

### Phase 2 → Phase 3 Integration Contract

When agent services are created as **new top-level directories** (`discovery-agent-svc/`, `intelligence-agent-svc/`):
1. The orchestrator calls them via the `url` field in manifest nodes
2. Agent services are stateless REST APIs — they receive state, process, and return results
3. **No changes needed in `ai-brand-automator/` or `pipeline-orchestrator-svc/`** — just add the agent URLs to manifest node definitions
4. Each agent gets its own `Dockerfile`, `requirements.txt`, and `main.py`
5. `deployment/docker-compose.yml` will be updated to include the new services

### Mock Mode (Before Downstream Services Exist)

The `OrchestratorDispatcher` supports a **mock mode** for development:

```python
# When ORCHESTRATOR_URL is empty or unreachable:
# - dispatch() returns True immediately
# - Job stays in QUEUED status
# - Developer can manually call the callback endpoint to simulate orchestrator behavior
```

This allows full end-to-end testing of the core-api-service without any downstream services running.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Orchestrator service not ready | High | Medium | OrchestratorDispatcher has graceful fallback mode — returns mock data when `ORCHESTRATOR_URL` is not reachable. All backend code testable independently. |
| Callback security | Medium | High | Use shared secret token + optionally allowlist orchestrator IP. Don't expose callback through Kong. |
| Long-running jobs | Medium | Medium | `check_stale_jobs` periodic task marks stale jobs as failed. Frontend stops polling after max attempts. |
| Large result_data payloads | Low | Medium | JSONField has no size limit in PostgreSQL. Consider streaming for very large results in future. |
| RBAC misconfiguration | Low | High | Comprehensive RBAC tests for every endpoint × role combination. |
| Cross-service tenant leak | Low | Critical | `tenant_context` in dispatch payload scopes all downstream data access. Integration tests verify tenant isolation end-to-end. |
| Agent service latency | Medium | Medium | Per-node timeout in manifest config. Orchestrator enforces max job duration (30 min). `check_stale_jobs` catches runaway pipelines. |
| Manifest schema drift | Medium | Medium | Serializer validates node structure (type, url, handler). Integration tests cover all 4 seed manifests. Breaking changes require version bump. |

---

## Estimated Effort

| Phase | Effort | Cumulative |
|-------|--------|------------|
| Phase 1: Backend Foundation | 1-2 hours | 1-2h |
| Phase 2: Serializers (HLD v6.0 node validation) | 2-3 hours | 3-5h |
| Phase 3: Views + URLs | 2-3 hours | 5-8h |
| Phase 4: Service Layer + Celery (tenant context, dispatch) | 2-3 hours | 7-11h |
| Phase 5: Callback (+ intent routing resolution) | 1-2 hours | 8-13h |
| Phase 6: Unit Testing (16 serializer + 13 service + 12 model + 7 task) | 4-5 hours | 12-18h |
| Phase 7: Integration Testing (RBAC + callback + lifecycle + tenant) | 3-4 hours | 15-22h |
| Phase 8: Frontend | 4-6 hours | 19-28h |
| Phase 9: Deployment | 2-3 hours | 21-31h |
| **Total** | **~21-31 hours** | |

---

## Dependencies & Assumptions

1. **No external orchestrator needed for Phase 1-7**: All backend work is self-contained. The `OrchestratorDispatcher` will work in "mock mode" when the orchestrator service isn't running.
2. **Existing fixtures are reusable**: All tenant/membership fixtures from `conftest.py` work with the new app.
3. **No database schema changes beyond the migration**: Using shared-schema FK filtering (same as all other apps).
4. **Kong needs no changes**: Covered by existing catch-all route.
5. **The `pipeline-orchestrator-svc` (LangGraph microservice)** will be a **separate top-level directory** (`Prevision_WS/pipeline-orchestrator-svc/`) — implemented in Phase 2. This plan covers only the Django API layer inside `ai-brand-automator/orchestration/`.
6. **Agent services (`discovery-agent-svc`, `intelligence-agent-svc`)** will be **separate top-level directories** — implemented in Phase 3. Their URLs are pre-configured in seed manifests but resolve to mock/unreachable endpoints until deployed.
7. **Manifest schema follows HLD v6.0**: The `nodes` + `edges` format (not the older `agents` format) is the canonical schema. Serializer validation enforces this.
8. **Intent routing is the orchestrator's responsibility**: The core-api-service dispatches jobs; the orchestrator decides which manifest/pipeline to use when `manifest` is null.
9. **Tenant context is always passed to the orchestrator**: Even if downstream services don't use it yet, the dispatch payload includes `tenant_context` for future-proofing.
10. **The `AnalysisJob.manifest` FK is nullable**: This supports the auto-detect/intent-routing scenario where the orchestrator selects the manifest.
