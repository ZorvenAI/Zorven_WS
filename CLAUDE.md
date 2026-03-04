# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Brand Automator is a **multi-tenant SaaS platform** for AI-powered brand building. Django REST Framework backend + Next.js 15 frontend + 9 Python FastAPI microservices, connected via Kafka event streaming and HTTP callbacks. AI powered by Google Gemini 2.0 Flash and Anthropic Claude. ~2,950+ tests across all components.

## Monorepo Layout

```
ai-brand-automator/              # Django 4.2 backend (DRF, JWT, django-tenants)
ai-brand-automator-frontend/     # Next.js 15 + React 19 + TypeScript + Tailwind v4
pipeline-orchestrator-svc/       # FastAPI — sequential pipeline execution (port 8010)
discovery-agent-svc/             # FastAPI — Web research via Tavily (port 8020)
intelligence-agent-svc/          # FastAPI — ISO 10668 brand valuation (port 8030)
chat-titling-worker/             # FastAPI — Auto-titles chat sessions (port 8040)
content-agent-service/           # FastAPI — SEO/AEO/GEO blog authoring (port 8050)
social-agent-service/            # FastAPI — Social media promotion (port 8060)
rag-uploader-agent-service/      # FastAPI — RAG document archival (port 8070)
brand-equity-calculator-svc/     # FastAPI — Public brand equity calc, Anthropic Claude (port 8090)
odoo-mcp-server-svc/            # FastAPI — Odoo ERP MCP bridge, 101 tools (port 8095)
vendor/odoo/community/           # Git submodule — Odoo Community Edition 19.0
deployment/                      # Master docker-compose, Kong config, scripts
docs/                            # Architecture docs
```

Each microservice has its own `CLAUDE.md` — read it before modifying that service. Services with `CLAUDE.md`: pipeline-orchestrator-svc, discovery-agent-svc, intelligence-agent-svc, chat-titling-worker, content-agent-service, social-agent-service, brand-equity-calculator-svc, odoo-mcp-server-svc. Missing: rag-uploader-agent-service.

## Build, Run, and Test Commands

### Backend (Django)

```bash
cd ai-brand-automator && source ../.venv/bin/activate

# Run server
python manage.py runserver 0.0.0.0:8001

# Tests
pytest -v                                    # All ~2075 tests
pytest automation/tests/ -v                  # Single app
pytest media_curation/tests/test_views.py -v # Single file
pytest -k "test_my_function" -v              # Single test by name
pytest -m unit                               # Unit tests only
pytest -m property                           # Hypothesis property tests
pytest --cov=. --cov-report=term-missing     # With coverage

# Format & lint (must pass before committing)
black .
flake8 .

# Migrations (NEVER use plain `migrate`)
python manage.py makemigrations
python manage.py migrate_schemas --shared --noinput

# Seed pipeline manifests (idempotent, run after manifest changes)
python manage.py seed_manifests
python manage.py seed_subscription_plans        # Seed Stripe plans
python manage.py check                          # Django system check

# Celery workers (6 queues: celery, high_priority, low_priority, orchestration, ingestion, curation)
celery -A brand_automator worker -l info                       # Default queue
celery -A brand_automator worker -Q orchestration -l info      # Orchestration queue
celery -A brand_automator worker -Q ingestion -l info          # Ingestion queue
celery -A brand_automator worker -Q curation -l info           # Curation queue
celery -A brand_automator beat -l info                         # Scheduler (60s: publish_scheduled_posts, 5m: check_stale_jobs)
```

### Frontend (Next.js)

```bash
cd ai-brand-automator-frontend

npm run dev          # Dev server on :3000
npm run build        # Production build (also serves as type check)
npm run lint         # ESLint
npm test             # Jest (60% coverage threshold)
npx tsc --noEmit     # TypeScript check only
```

### Microservices (all FastAPI + Python 3.12)

Each microservice follows the same pattern:
```bash
cd <service-dir>
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port <PORT> --reload

# Tests
pytest tests/ -v                      # All tests
pytest tests/ -m "not integration" -v # Unit only (no Redis/Kafka)
pytest tests/test_file.py -v          # Single file

# Format
black app/ tests/
```

### Full Stack (Docker Compose)

```bash
cd deployment

docker compose up --build                                     # Core services
docker compose --profile with-kafka up --build                # + Kafka streaming
docker compose --profile with-kafka --profile with-db up      # + Local PostgreSQL
docker compose down -v                                        # Tear down
```

**Service ports**: Kong 8000, Backend 8001 (internal only in Docker), Kong Admin 8001 (Docker only), Frontend 3000, Orchestrator 8010, Discovery 8020, Intelligence 8030, Titling 8040, Content 8050, Social 8060, RAG Uploader 8070, MCP 8085, Kafka UI 8080, Brand Equity 8090, Odoo MCP 8095

**Frontend Docker build** requires `output: "standalone"` in `next.config.ts`. Without it, the Dockerfile `COPY --from=builder /app/.next/standalone` step fails.

## Architecture

### Request Flow

```
Browser → Next.js (:3000) → apiClient (JWT auto-refresh) → Kong Gateway (:8000)
  → JWT validation, CORS, rate limiting → Django Backend (:8001) → Serializer → Model → PostgreSQL
```

### Pipeline Flow

```
Django dispatches job → pipeline-orchestrator-svc (:8010) → direct sequential execution
  → discovery-agent-svc (:8020) → research
  → intelligence-agent-svc (:8030) → brand valuation
  → content-agent-service (:8050) → blog authoring
  → social-agent-service (:8060) → social posting
  → rag-uploader-agent-service (:8070) → RAG document archival
  → Callback → Django AnalysisJob (atomic update)
```

When `ORCHESTRATION_KAFKA_ENABLED=false` (default), dispatch is HTTP. When `true`, dispatch goes through `pipeline-trigger-topic`. When Kafka is unavailable, system falls back to HTTP dispatch and Celery tasks for the data pipeline. Related env vars: `KAFKA_CONSUMERS_ENABLED` (controls Celery Kafka consumers), `ONBOARDING_KAFKA_ENABLED` (controls file upload Kafka publishing).

**Two pipeline modes:**
- **Chat (auto-detect)**: Dispatched without a manifest. `PipelineComposer` uses Gemini function-calling to dynamically compose a pipeline from the node catalog. Chat ALWAYS uses this mode.
- **Pipeline UI (manifest-driven)**: Dispatched with a `PipelineManifest` from `seed_manifests.py`. Fixed DAG defined in the manifest JSON.

**Per-node progress tracking**: The `JobExecutor` (`pipeline-orchestrator-svc/app/services/job_executor.py`) executes nodes **sequentially** in topological order (Kahn’s algorithm) via a simple for-loop. Before each node it sends a `running` progress callback; after each node it sends a `done` callback. This replaces the previous LangGraph `ainvoke`/`astream` approach which failed to fire per-node callbacks reliably on Railway. LangGraph remains a dependency but is **not used for execution**. Django's `result_handler.py` updates the DB and Redis cache with `current_node` and `progress_percent` on every callback. Frontend polls `/quick-status` every 3s via `usePollingJob`.

**Cancel mechanism**: Sets `cancel:{job_id}` key in Redis with 1-hour TTL. The executor checks this flag before each node in the sequential loop.

**Dynamic skill loading**: `pipeline-orchestrator-svc/skills/` contains 41 `.md` skill files (15 general + 26 Odoo-specific). The skill router (`pipeline-orchestrator-svc/app/skills/`) resolves and injects relevant skills per-node at execution time based on user intent. Skills provide contextual LLM instructions to agent services.

**Social agent publishing**: Social agent generates content via Gemini, then delegates actual platform publishing to Django's MCP server (via `SOCIAL_MCP_SERVER_URL`), which has per-platform SDK wrappers.

### Data Pipeline (Hexagonal Architecture)

```
Upload → data_ingestion → Kafka → media_curation → Kafka → rag_index (Vertex AI)
```

Pipeline apps (`data_ingestion/`, `media_curation/`, `rag_index/`) use **Pydantic domain models (NOT Django ORM)**, ABC ports, and concrete adapters. Never import Django ORM in these apps' domain layers. Each follows:
```
{app}/domain/    # Pydantic models
{app}/ports/     # ABC interfaces (StoragePort, etc.)
{app}/adapters/  # Concrete implementations (GCSStorageAdapter, KafkaProducerAdapter)
{app}/services/  # Business logic
{app}/factory.py # DI wiring
```

### Multi-Tenancy

Schema-based via `django-tenants`. All models have a nullable `tenant` FK. Most apps run in the shared (public) schema. The `files` app runs in per-tenant schemas as a `TENANT_APP`.

### Service-to-Service Authentication

| Header | Direction | Purpose |
|--------|-----------|---------|
| `X-Service-Token` | Django → Orchestrator | Dispatch and cancel |
| `X-Callback-Token` | Orchestrator → Django | Callback authentication |
| `X-Worker-Token` | Chat Titling Worker → Django | Title update |
| `X-Service-Token` | Content/Social Agent → Django | Blog/post creation |
| `X-Tenant-ID` | Content/Social Agent → Django | Tenant routing for blog/post creation |
| *(none)* | Browser → Brand Equity Calculator | **Public/unauthenticated** endpoint |
| `X-Tenant-ID` | Orchestrator → Odoo MCP Server | Tenant routing for Odoo operations |

### Redis Database Allocation

DB 0: Django/Celery, DB 1: Orchestrator, DB 2: Discovery, DB 3: Intelligence, DB 4: Titling, DB 5: Content, DB 6: Social, DB 7: RAG Uploader, DB 8: Brand Equity, DB 9: Odoo MCP

### Microservice Layout Convention

All 9 agent microservices follow this structure:
```
{service}/app/
├── api/          # FastAPI routes + Pydantic request/response schemas
├── core/         # Config (Pydantic BaseSettings with env prefix), logging
├── cache/        # RedisManager (service-specific key patterns)
├── logic/        # Business logic (domain-specific algorithms)
├── messaging/    # Kafka producer/consumer + event schemas
├── services/     # Executor (main entry point), API clients
└── main.py       # FastAPI application with lifespan management
```

Each service has its own env var prefix (e.g., `DISCOVERY_`, `INTELLIGENCE_`, `CONTENT_`, `SOCIAL_`, `TITLING_`, `RAG_UPLOADER_`, `BRAND_EQUITY_`, `ODOO_MCP_`).

### Kafka Topics

| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `pipeline-trigger-topic` | Django (Celery) | Orchestrator | Pipeline dispatch |
| `pipeline-result-topic` | Orchestrator | Django (Celery) | Job results |
| `agent-trace-topic` | Orchestrator nodes | Django (Celery) | Real-time node progress/thoughts |
| `data-ingestion-topic` | `data_ingestion` app | `media_curation` consumer | File processing pipeline |
| `media-curation-topic` | `media_curation` consumer | `rag_index` consumer | RAG indexing pipeline |
| `discovery-audit-topic` | Discovery agent | — | Discovery audit trail |
| `valuation-audit-logs` | Intelligence agent | — | Valuation audit trail |
| `content-published-topic` | Content agent | — | Content publish events |
| `social-audit-topic` | Social agent | — | Social publish audit trail |
| `chat-titling-topic` | Django | Titling worker | Chat session titling |
| `odoo-mcp-audit-topic` | Odoo MCP server | — | Odoo tool call audit trail |
| `odoo-tenant-events-topic` | Odoo MCP server | — | Odoo tenant lifecycle events |
| `tenant-provisioning-topic` | — | Odoo MCP server | New tenant provisioning |

## Critical Code Patterns

### Multi-Tenancy Defensive Access (ALWAYS follow this)

```python
# Query — backward-compatible with pre-tenant data
from django.db.models import Q
tenant = getattr(request, 'tenant', None)  # NEVER request.tenant directly
if tenant:
    qs = Model.objects.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
else:
    qs = Model.objects.filter(tenant__isnull=True)

# Create — always attach tenant
obj = Model.objects.create(tenant=getattr(request, 'tenant', None), ...)
```

### Django Models — Always Include

```python
tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, null=True, blank=True, related_name="%(class)ss")
created_at = models.DateTimeField(auto_now_add=True)
updated_at = models.DateTimeField(auto_now=True)

def __str__(self):
    return self.name  # Always define __str__

class Meta:
    ordering = ["-created_at"]
```

Use `UniqueConstraint` (not deprecated `unique_together`).

### Django ViewSets

Use `select_related` on FK querysets, `get_serializer_class()` for action-specific serializers, `perform_create()` for tenant attachment.

### Django Tests — Always Set SERVER_NAME

```python
@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client
```

### Orchestration Callbacks — Atomic Updates

```python
# Callback endpoint uses X-Callback-Token auth, not JWT
with transaction.atomic():
    job = AnalysisJob.objects.select_for_update().get(job_id=job_id)
    # update fields...
    job.save(update_fields=update_fields)
```

### Frontend — Route Protection and API Calls

```tsx
'use client';
import { useAuth } from '@/hooks/useAuth';
import { apiClient } from '@/lib/api';  // NEVER raw fetch()

export default function MyPage() {
  useAuth();
  // Guard hydration for tenant-role-dependent UI:
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => { setHasMounted(true); }, []);
  if (!hasMounted) return <LoadingSpinner />;
  // ...
}
```

### Frontend Polling (setTimeout, not setInterval)

```tsx
// usePollingJob.ts — prevents overlapping fetches
const poll = async () => {
  await fetchJob();
  if (status !== 'completed' && status !== 'failed') {
    timer = setTimeout(poll, intervalMs);
  }
};
```

### File Upload Deduplication

Backend: `UniqueConstraint(fields=["tenant", "company", "file_name"])` on `BrandAsset`. Returns HTTP 409 with existing asset info. Frontend catches via `DuplicateFileError` from `@/lib/errors.ts`.

### Input Validation

Use `sanitize_text_input()`, `sanitize_ai_prompt()`, `validate_file_upload()` from `brand_automator/validators.py`. Validate callback payloads (`progress`, `result_data`) ≤ 1 MB in `CallbackSerializer`.

### Frontend Design System

Use "Digital Twilight" dark theme classes: `glass-card`, `bg-brand-midnight`, `text-brand-electric`, `text-brand-silver`, `btn-primary`. Icons from `lucide-react`. See `ai-brand-automator-frontend/DESIGN_SYSTEM.md`.

## Non-Negotiable Rules

### Backend
- **Env vars**: Always `decouple.config()` with defaults — NEVER `os.environ`
- **Middleware order**: `CorsMiddleware` MUST be FIRST (before `TenantMainMiddleware`). Full order:
  ```
  CorsMiddleware → DefaultTenantMiddleware → SecurityMiddleware → WhiteNoiseMiddleware
  → ... standard Django ... → KongAuthenticationMiddleware → SecurityMiddleware
  → RequestValidationMiddleware → RateLimitMiddleware
  ```
- **MIME types**: Always use explicit MIME maps — Docker containers lack `/etc/mime.types`
- **Encrypted tokens**: OAuth tokens in `_access_token` columns, exposed via `@property` using `encrypt_token()`/`decrypt_token()`
- **Format**: Black (88 char lines) + Flake8
- **Dispatch errors**: 4xx → non-retryable (mark FAILED), 5xx/timeout → retryable (leave QUEUED)
- **SSRF prevention**: External URLs in pipeline manifests validated against `ALLOWED_URL_PREFIXES`
- **DB SSL**: `sslmode=require`, `channel_binding=require` for Neon

### Frontend
- **API calls**: Always `apiClient` from `@/lib/api` — NEVER raw `fetch()`
- **TypeScript**: Strict mode, path alias `@/*` → `./src/*`, never use `any` — use `unknown` and narrow with type guards
- **ESLint only** (no Prettier)
- **Components**: Functional components only, no class-based React

## Key Files

| Purpose | Path |
|---------|------|
| Django settings | `ai-brand-automator/brand_automator/settings.py` |
| URL routing | `ai-brand-automator/brand_automator/urls.py` |
| Middleware (Kong auth) | `ai-brand-automator/brand_automator/middleware.py` |
| Input validators | `ai-brand-automator/brand_automator/validators.py` |
| Custom auth views | `ai-brand-automator/brand_automator/auth_views.py` |
| AI service (Gemini) | `ai-brand-automator/ai_services/services.py` |
| OAuth encryption | `ai-brand-automator/automation/encryption.py` |
| MCP server (23 tools) | `ai-brand-automator/automation/mcp_server.py` |
| Test fixtures (Kafka mock, tenant setup) | `ai-brand-automator/conftest.py` |
| Celery config + task routes | `ai-brand-automator/brand_automator/celery.py` |
| Orchestration views + callbacks | `ai-brand-automator/orchestration/views.py` |
| Orchestration dispatch service | `ai-brand-automator/orchestration/services.py` |
| Pipeline manifest seeder | `ai-brand-automator/orchestration/management/commands/seed_manifests.py` |
| Pipeline result handler | `ai-brand-automator/orchestration/result_handler.py` |
| Orchestrator graph builder | `pipeline-orchestrator-svc/app/factory/graph_builder.py` |
| Orchestrator job executor | `pipeline-orchestrator-svc/app/services/job_executor.py` |
| Pipeline node tracker | `pipeline-orchestrator-svc/app/nodes/tracked.py` |
| Pipeline composer (auto-detect) | `pipeline-orchestrator-svc/app/nodes/internal/pipeline_composer.py` |
| Node registry (all available nodes) | `pipeline-orchestrator-svc/app/factory/node_registry.py` |
| Skill loader + router | `pipeline-orchestrator-svc/app/skills/` |
| Skill definitions (41 .md files) | `pipeline-orchestrator-svc/skills/` |
| Odoo MCP tool registry | `odoo-mcp-server-svc/app/tools/registry.py` |
| Odoo MCP RBAC engine | `odoo-mcp-server-svc/app/rbac/engine.py` |
| Odoo MCP role definitions (17 YAML) | `odoo-mcp-server-svc/config/roles/` |
| Frontend API client | `ai-brand-automator-frontend/src/lib/api.ts` |
| Frontend error types | `ai-brand-automator-frontend/src/lib/errors.ts` |
| Tenant context | `ai-brand-automator-frontend/src/contexts/TenantContext.tsx` |
| Tenant role hook | `ai-brand-automator-frontend/src/hooks/useTenantRole.ts` |
| Polling hook | `ai-brand-automator-frontend/src/hooks/usePollingJob.ts` |
| Pipeline graph UI | `ai-brand-automator-frontend/src/components/pipelines/PipelineGraph.tsx` |
| Orchestration types (FE) | `ai-brand-automator-frontend/src/types/orchestration.ts` |
| Frontend orchestration helpers | `ai-brand-automator-frontend/src/lib/orchestration.ts` |
| Frontend env config | `ai-brand-automator-frontend/src/lib/env.ts` |
| Onboarding pipeline service | `ai-brand-automator/onboarding/services.py` |
| Backend Procfile (9 processes) | `ai-brand-automator/Procfile` |
| Architecture overview | `ARCHITECTURE.md` |
| Copilot instructions | `.github/copilot-instructions.md` |
| Scoped instructions (backend/frontend/pipeline/testing) | `.github/instructions/` |
| Debug skills (pipeline, tenant, social) | `.github/skills/` |
| Agent boundaries | `AGENTS.md` |

## Commit Messages

Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`

## Testing Boundaries

- **Kafka**: Mocked at import time via `sys.modules` patching in `conftest.py`
- **Gemini AI**: Falls back to mock data when `GOOGLE_API_KEY` is absent
- **GCS**: Mocked via `unittest.mock.patch` on `GCSService`
- **Email**: Redirected to `locmem.EmailBackend` (autouse fixture)
- **Orchestrator**: Mocked via `unittest.mock.patch` on `OrchestratorDispatcher`
- **Microservice integration tests**: Marked with `@pytest.mark.integration` (require Redis)
- **Test markers**: `unit`, `integration`, `property`, `hypothesis`, `slow`, `skip_ci`, `gcp` (real GCP creds), `asyncio`
- **Test pyramid**: 70% unit / 25% integration / 5% property

## Do Not Modify

- `docs/LICENSE.md`, `credentials/`, `db.sqlite3` — Protected files
- `.github/workflows/ci-cd.yml` — CI pipeline (coordinate with team)
- `deployment/config/kong/` — Kong gateway config

## Modify With Caution

- `brand_automator/settings.py` — Middleware order is critical
- `brand_automator/middleware.py` — Security-sensitive
- `automation/encryption.py` — Changes break existing encrypted OAuth tokens
- Existing migration files — Never edit, always create new ones
- `conftest.py` — Only add fixtures, never remove
- Each microservice dir — Read its `CLAUDE.md` before modifying

## CI/CD

GitHub Actions: 8 jobs (backend-tests, media-curation, orchestrator-tests, discovery-agent-tests, intelligence-agent-tests, frontend-tests, integration-tests, build-images). Auto-deploy to Railway on `main` merge with change detection (only redeploys changed services). Backend CI runs `black --check .`, `flake8 .`, `pytest --cov`, and MCP server tests.
