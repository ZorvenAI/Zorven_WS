# ARCHITECTURE.md — AI Brand Automator

> The Map: High-level system architecture for long-horizon reasoning. Shows how data flows through the platform.

## System Overview

AI Brand Automator is a multi-tenant SaaS platform where users onboard companies, upload brand assets, and the AI generates brand strategies, manages social media, schedules content, runs multi-agent analysis pipelines, and integrates Google Business Profiles. The platform consists of a Django backend, Next.js frontend, and 6 FastAPI agent microservices orchestrated via LangGraph.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              USER BROWSER                                    │
│                                                                              │
│   Next.js 15 (React 19 + TypeScript + Tailwind v4)  — Port 3000             │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│   │  Auth    │ │ Onboard  │ │Dashboard │ │ AI Chat  │ │ Social/Automation│  │
│   │  Pages   │ │ Wizard   │ │+Pipelines│ │+Assistant│ │  Pages           │  │
│   └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────────────┘  │
│        └─────────────┴─────────────┴─────────────┴───────────┘               │
│                                    │                                         │
│                          apiClient (JWT auto-refresh)                        │
└────────────────────────────────────┼─────────────────────────────────────────┘
                                     │ HTTPS
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                       KONG GATEWAY — Port 8000                             │
│              JWT Auth │ CORS │ Rate Limiting │ Request Logging              │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                     DJANGO BACKEND — Port 8001                             │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  /api/v1/                                                           │   │
│  │  ├── auth/           → Register, Login, JWT Refresh                 │   │
│  │  ├── (root)          → Companies, BrandAssets, Onboarding           │   │
│  │  ├── ai/             → Chat, Content Generation (Gemini 2.0 Flash)  │   │
│  │  ├── subscriptions/  → Stripe Plans, Checkout, Webhooks             │   │
│  │  ├── automation/     → Social Profiles, Content Calendar, Posting   │   │
│  │  ├── orchestration/  → Pipeline Jobs, Manifests, Callbacks (NEW)    │   │
│  │  ├── ingestion/      → File Processing Pipeline API                 │   │
│  │  ├── curation/       → Media Curation Pipeline API                  │   │
│  │  └── rag-index/      → Document Sync to Vertex AI                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  onboarding  │  │  ai_services │  │  automation  │  │orchestration │   │
│  │  Company +   │  │  Gemini AI   │  │  Social +    │  │  Manifests + │   │
│  │  Assets      │  │  Singleton   │  │  GBP + MCP   │  │  Jobs        │   │
│  └──────┬───────┘  └──────────────┘  └──────────────┘  └──────┬───────┘   │
│         │                                                      │           │
│         ▼                                                      ▼           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              DATA PIPELINE (Hexagonal Architecture)                 │   │
│  │                                                                     │   │
│  │  Upload → data_ingestion ──Kafka──► media_curation ──Kafka──► rag_index │
│  │           (validate +       │       (OCR, PII,        │      (Vertex AI │
│  │            extract)         │        AI enrich)       │       vectors)  │
│  │                             │                         │                 │
│  │         domain/ ports/ adapters/ (Pydantic, not ORM)                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬─────────────────────────────────────────────────┘
         │              │  │            │               │
         ▼              ▼  │            ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ PostgreSQL   │ │    Redis     │ │ Google Cloud  │ │   Kafka      │
│ (Neon)       │ │ (7 DBs for   │ │  Storage     │ │ (Event       │
│ Multi-tenant │ │  all services)│ │  2 Buckets   │ │  Streaming)  │
│ schemas      │ │              │ │ raw + curated │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
                       │
         ┌─────────────┼──────────────────────────────────────────┐
         │             ▼                                          │
         │  ┌────────────────────────────────────────────────┐    │
         │  │         AGENT MICROSERVICES (FastAPI)           │    │
         │  │                                                │    │
         │  │  ┌──────────────┐  ┌──────────────┐            │    │
         │  │  │  Pipeline    │  │  Discovery   │            │    │
         │  │  │  Orchestrator│  │  Agent       │            │    │
         │  │  │  :8010       │  │  :8020       │            │    │
         │  │  │  LangGraph   │  │  Tavily +    │            │    │
         │  │  │  Redis DB 1  │  │  Redis DB 2  │            │    │
         │  │  └──────────────┘  └──────────────┘            │    │
         │  │                                                │    │
         │  │  ┌──────────────┐  ┌──────────────┐            │    │
         │  │  │ Intelligence │  │ Chat Titling │            │    │
         │  │  │  Agent       │  │  Worker      │            │    │
         │  │  │  :8030       │  │  :8040       │            │    │
         │  │  │  ISO 10668   │  │  Gemini Flash│            │    │
         │  │  │  Redis DB 3  │  │  Redis DB 4  │            │    │
         │  │  └──────────────┘  └──────────────┘            │    │
         │  │                                                │    │
         │  │  ┌──────────────┐  ┌──────────────┐            │    │
         │  │  │  Content     │  │  Social      │            │    │
         │  │  │  Agent       │  │  Agent       │            │    │
         │  │  │  :8050       │  │  :8060       │            │    │
         │  │  │  SEO/AEO/GEO │  │  MCP Client  │            │    │
         │  │  │  Redis DB 5  │  │  Redis DB 6  │            │    │
         │  │  └──────────────┘  └──────────────┘            │    │
         │  └────────────────────────────────────────────────┘    │
         └────────────────────────────────────────────────────────┘
```

## Core Data Flows

### 1. User Registration & Onboarding

```
Browser → POST /api/v1/auth/register/
       → POST /api/v1/auth/login/ → JWT (access + refresh tokens)
       → POST /api/v1/companies/ (create company)
       → POST /api/v1/assets/ (upload brand assets → GCS)
       → POST /api/v1/companies/{id}/generate_brand_strategy/ (Gemini AI)
```

### 2. Brand Asset Upload & Processing

```
Frontend Upload                GCS Raw Bucket         Kafka Topics
    │                              │                      │
    ▼                              ▼                      ▼
apiClient.upload()  ─────►  BrandAsset ─────► raw-ingestion-topic
                            (model +              │
                             GCS blob)            ▼
                                          IngestionService
                                          (validate, extract text)
                                                  │
                                                  ▼
                                          curation-needed-topic
                                                  │
                                                  ▼
                                          CurationService
                                          (OCR, PII redact,
                                           AI enrichment)
                                                  │
                                                  ▼
                                          rag-sync-ready-topic
                                                  │
                                                  ▼
                                          RAG Index Service
                                          (Vertex AI vector store)
```

### 3. AI Chat Interaction

```
User Message → POST /api/v1/ai/chat/
             → GeminiAIService.generate_content()
             → Gemini 2.0 Flash API
             → Structured response (brand strategy, market analysis, etc.)
             → Stored in ChatHistory model
```

### 4. Social Media Posting

```
Content Calendar Entry (scheduled_time reached)
    │
    ▼
Celery Beat (every 60s) → publish_scheduled_posts task
    │
    ▼
SocialProfile.get_valid_access_token()
    │ (decrypt + auto-refresh if expired)
    ▼
Platform API (LinkedIn / Twitter / Facebook / Instagram)
    │
    ▼
Update post status → "published" / "failed"
```

### 5. OAuth Social Account Connection

```
Frontend → GET /api/v1/automation/{platform}/connect/
        → Redirect to platform OAuth page
        → Platform callback → POST /api/v1/automation/{platform}/callback/
        → Encrypt + store tokens (Fernet via SECRET_KEY)
        → SocialProfile created (status: "connected")
```

### 6. Stripe Subscription Flow

```
Frontend → GET /api/v1/subscriptions/plans/          → List available plans
         → POST /api/v1/subscriptions/checkout/       → Create Stripe checkout session
         → Redirect to Stripe Checkout
         → Stripe webhook → POST /api/v1/subscriptions/webhook/
         → Update Subscription model (active/canceled/past_due)
```

### 7. Pipeline Orchestration (Dispatch → Agents → Callback)

```
User submits analysis request (AI Assistant or Pipelines page)
    │
    ▼
POST /api/v1/orchestration/jobs/
    │
    ▼
AnalysisJob created (status: QUEUED)
    │
    ▼
Celery dispatch_job_task (orchestration queue)
    │
    ├──[HTTP]──► POST pipeline-orchestrator-svc:8010/v1/jobs/dispatch
    │     OR
    ├──[Kafka]─► pipeline-trigger-topic (when ORCHESTRATION_KAFKA_ENABLED=True)
    │
    ▼
Pipeline Orchestrator (LangGraph DAG)
    │
    ├──► External agent nodes (HTTP calls):
    │       discovery-agent-svc:8020   (web research)
    │       intelligence-agent-svc:8030 (brand valuation)
    │       content-agent-service:8050  (blog authoring)
    │       social-agent-service:8060   (social publishing)
    │       rag-uploader-agent-svc:8070 (RAG document archival)
    │
    ├──► Internal nodes (in-process):
    │       RouterNode, PlannerNode, StrategyNode, ReportNode
    │
    ├──► Progress callbacks per-node:
    │       PATCH /api/v1/orchestration/jobs/{job_id}/callback/
    │       (X-Callback-Token auth, atomic row locking)
    │
    ▼
AnalysisJob updated (status: COMPLETED, result_data populated)
    │
    ▼
Frontend polls quick-status → renders ResultDashboard / ThoughtTrace
```

### 8. Chat Auto-Titling

```
User sends first message → POST /api/v1/ai/chat/
    │
    ▼
Django publishes to chat-titling-topic (Kafka)
    │
    ▼
chat-titling-worker:8040 consumes topic
    │  (dedup via Redis: titling:processed:{session_id})
    ▼
Gemini Flash generates concise title
    │
    ▼
PATCH /api/v1/ai/chat-sessions/{id}/ (X-Worker-Token auth)
```

## App Responsibilities

| App | Responsibility | Architecture |
|-----|---------------|-------------|
| `brand_automator/` | Settings, middleware, auth views, URL routing, validators | Standard Django |
| `tenants/` | Tenant/Domain models for `django-tenants` | Standard Django |
| `onboarding/` | Company, BrandAsset models, onboarding wizard API, GCS upload | Standard Django |
| `ai_services/` | Gemini AI integration, chat history, content generation | Standard Django |
| `automation/` | Social profiles, content calendar, OAuth, MCP server, GBP | Standard Django |
| `subscriptions/` | Stripe plans, checkout, webhooks, subscription status | Standard Django |
| `files/` | GCS service (signed URLs, upload, delete), file browser | Standard Django |
| `data_ingestion/` | File validation, text extraction, Kafka producer | **Hexagonal** |
| `media_curation/` | OCR, PII redaction, AI enrichment, content routing | **Hexagonal** |
| `rag_index/` | Vertex AI vector store sync, document indexing | **Hexagonal** |
| `orchestration/` | Pipeline manifests, analysis jobs, dispatch, callbacks | Standard Django |
| `kafka_service/` | Shared Kafka consumer utilities | Standard Django |

## Multi-Tenancy Model

```
┌─────────────────────────────────────────────────┐
│              PUBLIC SCHEMA                       │
│                                                  │
│  Tenant ──► Domain (localhost, app.example.com)  │
│  User ──► Company ──► BrandAsset                 │
│  SocialProfile, ContentCalendar, AutomationTask  │
│  Subscription, Plan, ChatHistory                 │
│  PipelineManifest, AnalysisJob                   │
│  IngestionRecord, CurationRecord                 │
│                                                  │
│  All models have nullable tenant FK:             │
│  tenant = ForeignKey(Tenant, null=True)           │
└─────────────────────────────────────────────────┘

Most apps run in the public (SHARED) schema and query defensively by tenant FK; the `files` app runs in per-tenant schemas as a `TENANT_APP`.
```

### Tenant-Scoped GCS Buckets

Each tenant can have its own GCS buckets (optional overrides on the Tenant model):

```
Tenant Model:
  gcs_raw_bucket      → Per-tenant raw storage (CharField, blank)
  gcs_curated_bucket   → Per-tenant curated storage (CharField, blank)
  get_raw_bucket()     → Returns tenant bucket or falls back to GCS_RAW_BUCKET global
  get_curated_bucket() → Returns tenant bucket or falls back to GCS_CURATED_BUCKET global
```

### Redis Key Namespacing

All pipeline Redis keys are prefixed with `tenant_id` when available, ensuring data isolation:

```
data_ingestion:
  {tenant_id}:ingestion:dedupe:{event_id}     → Deduplication tracking
  {tenant_id}:ingestion:status:{trace_id}     → Processing status

media_curation:
  {tenant_id}:curation:status:{trace_id}      → Curation status
  {tenant_id}:curation:dedupe:{event_id}      → Deduplication
  curation:tenant:{tenant_id}                 → Tenant config

rag_index:
  {tenant_id}:rag_sync:status:{event_id}      → Sync status
  rag_sync:rate:{key}                         → Rate limiting (global, intentional)
```

Keys without tenant_id fall back to un-prefixed format for backward compatibility.

### Celery Tenant Scoping

- `publish_scheduled_posts` uses `select_related("tenant")` and logs tenant_id per post.
- `_update_asset_after_ingestion` and `_update_asset_status` filter BrandAsset queries by `tenant_id` (integer FK) when a valid tenant_id is provided.

### Defensive Access Pattern

All ViewSets use `getattr(request, 'tenant', None)` — never bare `request.tenant`.

**Creating objects** — always attach tenant:
```python
tenant = getattr(request, 'tenant', None)
obj = Model.objects.create(
    user=request.user,
    tenant=tenant,
    # ... other fields
)
```

**Querying objects** — use backward-compatible Q() pattern to include pre-existing records that have `tenant=NULL`:
```python
from django.db.models import Q

tenant = getattr(request, 'tenant', None)
if tenant:
    qs = Model.objects.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
else:
    qs = Model.objects.filter(tenant__isnull=True)
```

This pattern was applied across all automation views (PR #153) to fix content calendar entries and automation tasks not appearing after the multi-tenancy migration.

## Microservices Architecture

All 6 agent microservices are standalone FastAPI applications following a consistent layout:

```
{service}/
├── app/
│   ├── api/          → FastAPI routes + Pydantic request/response schemas
│   ├── core/         → Config (Pydantic BaseSettings with env prefix), logging
│   ├── cache/        → RedisManager (service-specific key patterns)
│   ├── logic/        → Business logic (domain-specific algorithms)
│   ├── messaging/    → Kafka producer/consumer + event schemas
│   ├── services/     → Executor (main entry point), API clients
│   └── main.py       → FastAPI application with lifespan management
├── tests/            → pytest suite (unit + integration markers)
├── Dockerfile        → Uvicorn-based container (python:3.12-slim)
└── requirements.txt
```

### Service-to-Service Authentication

| Header | Direction | Purpose |
|--------|-----------|---------|
| `X-Service-Token` | Django → Orchestrator | Dispatch and cancel authentication |
| `X-Callback-Token` | Orchestrator → Django | Callback authentication |
| `X-Worker-Token` | Chat Titling Worker → Django | Title update authentication |
| `X-Service-Token` | Content/Social Agent → Django | Blog/post creation |
| `X-Tenant-ID` | Content/Social Agent → Django | Tenant routing for blog/post creation |

### Redis Database Allocation

| DB | Service | Key Prefix Examples |
|----|---------|---------------------|
| 0 | Django Backend (Celery) | `celery-task-meta-*`, `job:status:{id}` |
| 1 | Pipeline Orchestrator | `orchestrator:job:*`, `orchestrator:graph:*` |
| 2 | Discovery Agent | `discovery:cache:*`, `discovery:page:*` |
| 3 | Intelligence Agent | `intel:benchmarks:*`, `intel:result:*` |
| 4 | Chat Titling Worker | `titling:processed:{session_id}` |
| 5 | Content Agent | `content:seo:*`, `content:result:*` |
| 6 | Social Agent | `social:result:*`, `social:rate:*` |
| 7 | RAG Uploader Agent | `uploader:dedupe:*`, `uploader:rate:*` |

## Kafka Topics

### Data Pipeline Topics
| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `raw-ingestion-topic` | Django onboarding | ingestion-consumer | File upload triggers |
| `curation-needed-topic` | data_ingestion | curation-consumer | Files ready for curation |
| `rag-sync-ready-topic` | media_curation | rag-index-consumer | Documents ready for indexing |
| `ingestion-dlq` | ingestion | manual review | Ingestion failures |

### Orchestration Topics
| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `pipeline-trigger-topic` | Django orchestration | pipeline-orchestrator-svc | Job dispatch via Kafka |
| `agent-trace-topic` | orchestrator | Django TraceConsumer | Real-time agent progress |
| `pipeline-result-topic` | orchestrator | Django ResultConsumer | Final pipeline results |
| `orchestration-dlq` | consumers | manual review | Orchestration failures |

### Chat & Infrastructure Topics
| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `chat-titling-topic` | Django ai_services | chat-titling-worker | Session title generation |
| `gateway-logs` | Kong | optional consumer | API gateway audit logs |
| `dlq-events` | pipeline consumers | manual review | General dead letter queue |

## Process Architecture (Procfile)

### Django Backend Processes
| Process | Role | Command |
|---------|------|---------|
| `web` | HTTP API server | Gunicorn (4 workers, 2 threads) |
| `worker` | General Celery worker | Default queue |
| `orchestration-worker` | Orchestration Celery worker | `orchestration` queue |
| `beat` | Celery scheduler | Every 60s: publish_scheduled_posts |
| `ingestion-worker` | Ingestion Celery worker | `ingestion` queue |
| `ingestion-consumer` | Kafka → Ingestion | `run_ingestion` command |
| `curation-worker` | Curation Celery worker | `curation` queue |
| `curation-consumer` | Kafka → Curation | `run_curation_consumer` command |
| `rag-index-consumer` | Kafka → RAG sync | `consume_sync_events` command |

### Agent Microservices (FastAPI + Uvicorn)
| Service | Port | Redis DB | Command |
|---------|------|----------|---------|
| `pipeline-orchestrator-svc` | 8010 | DB 1 | `uvicorn app.main:app --port 8010` |
| `discovery-agent-svc` | 8020 | DB 2 | `uvicorn app.main:app --port 8020` |
| `intelligence-agent-svc` | 8030 | DB 3 | `uvicorn app.main:app --port 8030` |
| `chat-titling-worker` | 8040 | DB 4 | `uvicorn app.main:app --port 8040` |
| `content-agent-service` | 8050 | DB 5 | `uvicorn app.main:app --port 8050` |
| `social-agent-service` | 8060 | DB 6 | `uvicorn app.main:app --port 8060` |
| `rag-uploader-agent-service` | 8070 | DB 7 | `uvicorn app.main:app --port 8070` |

## External Service Integration

| Service | Purpose | Auth Method |
|---------|---------|------------|
| Google Gemini 2.0 Flash | AI content generation | API key (`GOOGLE_API_KEY`) |
| Google Cloud Storage | File storage (2 default + per-tenant buckets) | Service account JSON |
| Stripe | Payments & subscriptions | Secret key + webhooks |
| LinkedIn API | OAuth + posting + analytics | OAuth 2.0 + page tokens |
| Twitter/X API | OAuth + posting + analytics | OAuth 2.0 |
| Facebook Graph API | OAuth + posting + analytics | OAuth 2.0 + page tokens |
| Instagram Graph API | OAuth + posting + analytics | Via Facebook page tokens |
| Google Business Profile | OAuth + posts + reviews | OAuth 2.0 |
| Apache Kafka | Event streaming (pipeline) | SASL/SSL or plaintext |
| Tavily API | Web search (Discovery Agent) | API key |
| Neon PostgreSQL | Primary database | Connection string + SSL |
| Redis | Celery broker + caching (7 DBs) | Connection URL |

## Testing Architecture

```
Django Backend (pytest ~2090 tests)
├── Unit tests (70%)        → Models, serializers, utils, encryption
├── Integration tests (25%) → Views with DB, API endpoints, Celery tasks
├── Property tests (5%)     → Hypothesis-based edge case discovery
└── Mocks                   → Kafka, GCS, Gemini AI, Email, Stripe, Orchestrator

Microservices (pytest ~628 tests)
├── pipeline-orchestrator-svc   (171 tests)
├── discovery-agent-svc         (179 tests)
├── intelligence-agent-svc      (100 tests)
├── social-agent-service        (89 tests)
├── content-agent-service       (55 tests)
└── chat-titling-worker         (34 tests)

Cross-Service Integration (tests/integration/, ~60 tests)
├── Phase 1: Contract tests     → API schema validation
├── Phase 2: Domain tests       → End-to-end pipeline scenarios
└── Phase 3: Stress tests       → Concurrent load, timeout behavior

Total: ~2770 tests
```

Key testing boundaries:
- **Kafka**: Mocked at import time via `sys.modules` patching in `conftest.py`
- **Gemini AI**: Falls back to mock data when `GOOGLE_API_KEY` is absent
- **GCS**: Mocked via `unittest.mock.patch` on `GCSService`
- **Email**: Redirected to `locmem.EmailBackend` (autouse fixture)
- **Orchestrator**: Mocked via `unittest.mock.patch` on `OrchestratorDispatcher`
- **Microservice integration tests**: Marked `@pytest.mark.integration` (require Redis)

## Deployment Topology (GCP Cloud Run)

Production runs on **Google Cloud Run** in project `zorven-503517`, region `us-central1`, served at **zorven.ai**. Railway has been retired.

```
Public DNS
├── zorven.ai / www.zorven.ai   → zorven-frontend    (Next.js)
└── api.zorven.ai               → zorven-backend     (Gunicorn)

Cloud Run services (zorven-*, 30 images)
├── zorven-backend            → ai-brand-automator/ (Gunicorn)
├── zorven-backend-ws         → ai-brand-automator/ (Daphne, WebSocket/ASGI)
├── zorven-celery-worker      → ai-brand-automator/ (celery worker)
├── zorven-celery-beat        → ai-brand-automator/ (celery beat)
├── zorven-frontend           → ai-brand-automator-frontend/ (Next.js standalone)
├── zorven-mlflow             → MLflow tracking + prompt registry
├── zorven-orchestrator       → pipeline-orchestrator-svc/ (Uvicorn)
├── zorven-<agent>            → one service per agent microservice (Uvicorn)
└── zorven-migrations         → Cloud Run Job (migrate_schemas, run pre-deploy)

Managed dependencies
├── Artifact Registry  → us-central1-docker.pkg.dev/zorven-503517/zorven
├── Memorystore Redis  → zorven-redis (reached via VPC connector zorven-connector)
├── Secret Manager     → runtime secrets, mounted as env vars
├── Service Account    → zorven-cloudrun@zorven-503517.iam.gserviceaccount.com
└── PostgreSQL         → Neon (external, sslmode=require + channel_binding=require)
```

**Frontend API resolution** (`ai-brand-automator-frontend/src/lib/env.ts`) is hostname-driven, not env-driven, in the browser: `zorven.ai`/`www.zorven.ai` → `api.zorven.ai`; a `*.run.app` host → the backend's direct Cloud Run URL; anything else → `<hostname>:8000` for local dev. `NEXT_PUBLIC_API_URL` is only consulted during SSR.

**CI/CD**: GitHub Actions → 10 test jobs (backend-tests, test-media-curation, orchestrator-tests, discovery-agent-tests, intelligence-agent-tests, odoo-mcp-server-tests, odoo-worker-tests, frontend-tests, integration-tests, build-images) → `docker-publish.yml` pushes images to GHCR (`ghcr.io/zorvenai`) → `deploy-gcp.yml` mirrors only changed images to Artifact Registry, runs the `zorven-migrations` job when the backend changed, then `gcloud run services update`s each affected service and health-checks it.

One-time infrastructure provisioning lives in `deployment/gcp/` as numbered scripts (`00-config.sh` … `11-verify.sh`, `deploy-all.sh`, `99-teardown.sh`).

## Frontend Hydration Safety

Client components that depend on `TenantContext` (which reads from `localStorage`) must guard against SSR/client hydration mismatches:

```tsx
// Gate role-dependent UI behind a mount flag
const [hasMounted, setHasMounted] = useState(false);
useEffect(() => { setHasMounted(true); }, []);
const canEdit = hasMounted ? tenantRole.canEdit : false;

// Or return a loading spinner until mounted
if (!hasMounted) return <LoadingSpinner />;
```

This pattern is applied in the automation page (PR #154), and should be used in any page that conditionally renders different HTML based on tenant role.
