# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Brand Automator is a **multi-tenant SaaS platform** for AI-powered brand building, live at **zorven.ai** (GCP Cloud Run, project `zorven-503517` / `us-central1`). Django REST Framework backend + Next.js 15 frontend + 27 Python FastAPI microservices, connected via Kafka event streaming and HTTP callbacks. AI powered by Google Gemini (default `gemini-3.5-flash`, set in `ai_services/services.py`) and Anthropic Claude.

**Social platform integrations** (all 5 complete): LinkedIn, Twitter/X, Facebook, Instagram, Google Business Profile — each with full OAuth, posting, scheduling, media upload, and analytics. Stripe subscriptions: Basic $29 / Pro $79 / Enterprise $199.

## Monorepo Layout

```
ai-brand-automator/              # Django 4.2 backend (DRF, JWT, django-tenants)
ai-brand-automator-frontend/     # Next.js 15 + React 19 + TypeScript + Tailwind v4
pipeline-orchestrator-svc/       # FastAPI — sequential pipeline execution (port 8010)
discovery-agent-svc/             # port 8020
market-research-agent-svc/       # port 8021
competitor-intel-agent-svc/      # port 8022
audience-persona-agent-svc/      # port 8023 (Claude Sonnet 4)
trend-cultural-agent-svc/        # port 8024
voc-agent-svc/                   # port 8025 (Claude Sonnet 4)
intelligence-agent-svc/          # port 8030
brand-positioning-agent-svc/     # port 8031 (Claude Sonnet 4, WF2)
brand-architecture-agent-svc/    # port 8032 (Claude Sonnet 4, WF2)
brand-personality-agent-svc/     # port 8033 (Claude Sonnet 4, WF2)
brand-naming-agent-svc/          # port 8034 (Claude Sonnet 4, WF2)
brand-story-agent-svc/           # port 8035 (Claude Sonnet 4, WF2)
chat-titling-worker/             # port 8040
campaign-architecture-agent-svc/ # port 8041 (Claude Sonnet 4, WF3)
creative-generation-agent-svc/   # port 8042 (Claude Sonnet 4, WF3)
ad-publishing-agent-svc/         # port 8043 (Claude Sonnet 4, WF3)
campaign-optimization-agent-svc/ # port 8044 + Celery Beat (Claude Sonnet 4, WF3)
intelligence-loop-agent-svc/     # port 8045 (WF3.5)
content-agent-service/           # port 8050
social-agent-service/            # port 8060
rag-uploader-agent-service/      # port 8070
brand-equity-calculator-svc/     # port 8090 (Anthropic Claude, public/unauthenticated)
odoo-mcp-server-svc/             # port 8095 (101 tools, RBAC)
odoo-worker-agent-svc/           # port 8100
prompt-optimization-svc/         # port 8110 (MLflow + GEPA)
onboarding-intelligence-agent-svc/ # port 8120 (STT + OCR + Gemini)
vendor/odoo/community/           # Git submodule — Odoo CE 19.0
deployment/                      # Docker Compose, Kong, GCP (has its own CLAUDE.md)
tests/integration/               # Cross-service integration tests (3 phases)
scripts/                         # One-off tooling (skill YAML validation, e2e scripts, prompt seeding)
spike-stt-v2/, spike-ws-gateway/ # Throwaway OIA spikes — not deployed, not in CI
```

Each microservice has its own `CLAUDE.md` — read it before modifying that service.

## Build, Run, and Test Commands

### Backend (Django)

```bash
cd ai-brand-automator && source ../.venv/bin/activate

python manage.py runserver 0.0.0.0:8001

pytest -v                                    # All tests
pytest automation/tests/ -v                  # Single app
pytest media_curation/tests/test_views.py -v # Single file
pytest -k "test_my_function" -v              # Single test by name
pytest -m unit                               # Unit tests only
pytest -m property                           # Hypothesis property tests
pytest --cov=. --cov-report=term-missing     # With coverage

black .                                      # Format (must pass before committing) — black==23.12.1, see below
flake8 .                                     # Lint (must pass before committing)
pytest -m "not property"                     # What CI runs (property tests run in a separate job)

# Migrations (NEVER use plain `migrate`)
python manage.py makemigrations
python manage.py migrate_schemas --shared --noinput

# Seed data (idempotent)
python manage.py seed_manifests              # Pipeline manifests
python manage.py seed_metrics                # Analytics MetricDefinitions
python manage.py seed_subscription_plans     # Stripe plans
python manage.py seed_sandbox_recommendations
python manage.py provision_data_stores       # Per-tenant data stores
python manage.py cache_health                # Redis cache health check

# Celery (6 queues: celery, high_priority, low_priority, orchestration, ingestion, curation)
celery -A brand_automator worker -l info
celery -A brand_automator worker -Q orchestration -l info
celery -A brand_automator beat -l info       # Schedule: CELERY_BEAT_SCHEDULE in settings.py (DatabaseScheduler)
```

Beat jobs: `publish_scheduled_posts` (60s), `check_stale_jobs` (5m), `sync_calendars` (3m), `refresh_calendar_tokens` (1h), `reconcile_rollups_task` (02:00 UTC). Kafka consumer tasks are only registered when `KAFKA_CONSUMERS_ENABLED=true`.

**Two Black versions.** The backend pins `black==23.12.1`; the microservices require `black>=24`. They format differently, so running the wrong one produces spurious diffs and fails CI's `black --check`. Use the version pinned in the requirements file of the directory you're working in.

### Frontend (Next.js)

```bash
cd ai-brand-automator-frontend

npm run dev          # Dev server on :3000
npm run build        # Production build (also type checks)
npm run lint         # ESLint
npm test             # Jest (60% coverage threshold)
npm test -- path/to/file.test.tsx   # Single test file
npm run test:e2e     # Playwright end-to-end
npx tsc --noEmit     # TypeScript check only
```

### Microservices (all FastAPI + Python 3.12)

```bash
cd <service-dir>
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port <PORT> --reload

pytest tests/ -v                      # All tests
pytest tests/ -m "not integration" -v # Unit only (no Redis/Kafka)
black app/ tests/
```

### Cross-Service Integration Tests

```bash
cd tests/integration
pytest phase1_contracts/ -v      # API contract tests
pytest phase2_domain/ -v         # Domain logic integration
pytest phase3_stress/ -v         # Stress/load tests
```

### Full Stack (Docker Compose)

```bash
cd deployment
docker compose up --build                                     # Core services
docker compose --profile with-kafka up --build                # + Kafka streaming
docker compose --profile with-kafka --profile with-db up      # + Local PostgreSQL
docker compose down -v                                        # Tear down
```

See `deployment/CLAUDE.md` for profiles, port mapping, and CI/CD details.

**Frontend Docker build** requires `output: "standalone"` in `next.config.ts` — without it the `COPY --from=builder /app/.next/standalone` step fails.

## Architecture

### Request Flow

```
Browser → Next.js (:3000) → apiClient (JWT auto-refresh) → Kong Gateway (:8000)
  → JWT validation, CORS, rate limiting → Django Backend (:8001) → Serializer → Model → PostgreSQL
```

### Pipeline Flow

```
Django dispatches job → pipeline-orchestrator-svc → sequential execution (Kahn's topological order)
  → WF1: discovery → market-research → competitor-intel → audience-persona → trend-cultural → voc → intelligence
  → WF2: brand-positioning → brand-architecture → brand-personality → brand-naming → brand-story
  → WF3: campaign-architecture → creative-generation → ad-publishing → campaign-optimization
  → WF3.5: intelligence-loop (extracts campaign learnings → RAG)
  → content → social → rag-uploader → odoo-worker
  → Callback → Django AnalysisJob (atomic update) → extract_metrics_task (analytics)
```

When `ORCHESTRATION_KAFKA_ENABLED=false` (default), dispatch is HTTP. When `true`, dispatch goes through `pipeline-trigger-topic`.

**Two pipeline modes:**
- **Chat (auto-detect)**: No manifest. `PipelineComposer` uses Gemini function-calling to dynamically compose a pipeline from the node catalog.
- **Pipeline UI (manifest-driven)**: Fixed DAG from `PipelineManifest` (`seed_manifests.py`).

**Per-node progress**: `JobExecutor` executes nodes sequentially via for-loop, sending `running`/`done` progress callbacks per node. Django's `result_handler.py` updates DB and Redis cache. Frontend polls `/quick-status` every 3s via `usePollingJob`.

**Cancel mechanism**: Sets `cancel:{job_id}` key in Redis (1-hour TTL). Executor checks before each node.

**Dynamic skill loading**: 155 `.md` skill files in `pipeline-orchestrator-svc/skills/`. Skill router resolves and injects relevant skills per-node at execution time.

### Data Pipeline (Hexagonal Architecture)

```
Upload → data_ingestion → Kafka → media_curation → Kafka → rag_index (Vertex AI)
```

Pipeline apps (`data_ingestion/`, `media_curation/`, `rag_index/`) use **Pydantic domain models (NOT Django ORM)**, ABC ports, and concrete adapters. Never import Django ORM in these apps' domain layers.

### The `apps/` Namespace Package

`ai-brand-automator/apps/` holds the Django side of OIA (Onboarding Intelligence Agent). Two apps live here:

| Package | App label | Purpose |
|---------|-----------|---------|
| `apps.onboarding` | **`onboarding_sessions`** | OIA session state, field provenance, consent |
| `apps.integrations` | `integrations` | Calendar connections, Google Calendar OAuth |

**App-label collision warning**: The top-level `onboarding/` owns the label `onboarding`. `apps.onboarding` registers as **`onboarding_sessions`** — use that label for migrations, `apps.get_model()`, and `related_name` targets.

**URL mounting** (`brand_automator/urls.py`): wizard at `path("")`, OIA sessions at `path("onboarding/")`, integrations at `path("integrations/")`.

**Event emission** (`apps/onboarding/events.py`): Only EVT-109 (`onboarding.provenance.reviewed`). Payload carries **no field values** (privacy constraint) — only `field_name`, `action`, `edit_distance`, `classification`. Gated on `ONBOARDING_KAFKA_ENABLED`.

### Service-to-Service Authentication

| Header | Direction | Purpose |
|--------|-----------|---------|
| `X-Service-Token` | Django → Orchestrator / Content/Social → Django | Dispatch, cancel, blog/post creation |
| `X-Callback-Token` | Orchestrator → Django | Callback authentication |
| `X-Worker-Token` | Chat Titling Worker → Django | Title update |
| `X-Tenant-ID` | Content/Social/Orchestrator → Django/Odoo MCP | Tenant routing |

Brand Equity Calculator is **public/unauthenticated** — no auth headers.

### Multi-Tenancy

Schema-based via `django-tenants`. All models have a nullable `tenant` FK. The `files` app is the only app in `TENANT_APPS` (per-tenant schemas); everything else runs in the shared (public) schema.

### Microservice Layout Convention

```
{service}/app/
├── api/          # FastAPI routes + Pydantic schemas
├── core/         # Config (Pydantic BaseSettings with env prefix)
├── cache/        # RedisManager
├── logic/        # Business logic
├── messaging/    # Kafka producer/consumer + event schemas
├── services/     # Executor (main entry), API clients
└── main.py       # FastAPI application with lifespan
```

Each service has its own env var prefix (e.g., `DISCOVERY_`, `CONTENT_`, `OIA_`).

## Critical Code Patterns

### Multi-Tenancy Defensive Access (ALWAYS follow this)

```python
from django.db.models import Q
tenant = getattr(request, 'tenant', None)  # NEVER request.tenant directly
if tenant:
    qs = Model.objects.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
else:
    qs = Model.objects.filter(tenant__isnull=True)

obj = Model.objects.create(tenant=getattr(request, 'tenant', None), ...)
```

### Django Models — Always Include

```python
tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, null=True, blank=True, related_name="%(class)ss")
created_at = models.DateTimeField(auto_now_add=True)
updated_at = models.DateTimeField(auto_now=True)

def __str__(self):
    return self.name

class Meta:
    ordering = ["-created_at"]
```

Use `UniqueConstraint` (not deprecated `unique_together`).

### Django Tests — Always Set SERVER_NAME

```python
@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client
```

### DRF ViewSet Conventions

```python
class MyViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        qs = Model.objects.select_related('company', 'tenant')  # Always select_related on FKs
        if tenant:
            return qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
        return qs.filter(tenant__isnull=True)

    def get_serializer_class(self):
        if self.action == 'list':
            return ModelListSerializer          # Action-specific serializers
        return ModelDetailSerializer

    def perform_create(self, serializer):
        serializer.save(tenant=getattr(self.request, 'tenant', None))  # Attach tenant on create
```

### Orchestration Callbacks — Atomic Updates

```python
with transaction.atomic():
    job = AnalysisJob.objects.select_for_update().get(job_id=job_id)
    job.save(update_fields=update_fields)
```

### Frontend — Route Protection and API Calls

```tsx
'use client';
import { useAuth } from '@/hooks/useAuth';
import { apiClient } from '@/lib/api';  // NEVER raw fetch()

export default function MyPage() {
  useAuth();
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => { setHasMounted(true); }, []);
  if (!hasMounted) return <LoadingSpinner />;
}
```

### Frontend Polling (setTimeout, not setInterval)

```tsx
const poll = async () => {
  await fetchJob();
  if (status !== 'completed' && status !== 'failed') {
    timer = setTimeout(poll, intervalMs);
  }
};
```

### Input Validation

Use `sanitize_text_input()`, `sanitize_ai_prompt()`, `validate_file_upload()` from `brand_automator/validators.py`. Validate callback payloads ≤ 1 MB in `CallbackSerializer`.

### File Upload Deduplication

`UniqueConstraint(fields=["tenant", "company", "file_name"])` on `BrandAsset`. Returns HTTP 409. Frontend catches via `DuplicateFileError` from `@/lib/errors.ts`.

## Non-Negotiable Rules

### Backend
- **Env vars**: Always `decouple.config()` with defaults — NEVER `os.environ`
- **Middleware order** (positional — do not reorder):
  1. `CorsMiddleware` (MUST be first)
  2. `DefaultTenantMiddleware` (falls back to public schema)
  3. `SecurityMiddleware`
  4. `WhiteNoiseMiddleware`
  5. …standard Django…
  6. `KongAuthenticationMiddleware` (after `AuthenticationMiddleware`)
  7. `SecurityMiddleware` (custom)
  8. `RequestValidationMiddleware`
  9. `RateLimitMiddleware`
- **MIME types**: Always use explicit MIME maps — Docker containers lack `/etc/mime.types`
- **Encrypted tokens**: OAuth tokens in `_access_token` columns, exposed via `@property` using `encrypt_token()`/`decrypt_token()`
- **Format**: Black (88 char lines) + Flake8
- **Dispatch errors**: 4xx → non-retryable (mark FAILED), 5xx/timeout → retryable (leave QUEUED)
- **SSRF prevention**: External URLs validated against `ALLOWED_URL_PREFIXES`
- **DB SSL**: `sslmode=require`, `channel_binding=require` for Neon

### Frontend
- **API calls**: Always `apiClient` from `@/lib/api` — NEVER raw `fetch()`
- **TypeScript**: Strict mode, path alias `@/*` → `./src/*`, never use `any` — use `unknown` and narrow
- **ESLint only** (no Prettier)
- **Components**: Functional only, no class-based React
- **Design system**: "Digital Twilight" dark theme — `glass-card`, `bg-brand-midnight`, `text-brand-electric`, `text-brand-silver`. Icons from `lucide-react`. Charts via `recharts`. See `DESIGN_SYSTEM.md`.

## Key Files

| Purpose | Path |
|---------|------|
| Django settings | `ai-brand-automator/brand_automator/settings.py` |
| URL routing | `ai-brand-automator/brand_automator/urls.py` |
| Middleware (Kong auth) | `ai-brand-automator/brand_automator/middleware.py` |
| Input validators | `ai-brand-automator/brand_automator/validators.py` |
| AI service (Gemini) | `ai-brand-automator/ai_services/services.py` |
| OAuth encryption | `ai-brand-automator/automation/encryption.py` |
| MCP server (23 tools) | `ai-brand-automator/automation/mcp_server.py` |
| Test fixtures | `ai-brand-automator/conftest.py` |
| Celery config + routes | `ai-brand-automator/brand_automator/celery.py` |
| Orchestration dispatch | `ai-brand-automator/orchestration/services.py` |
| Pipeline result handler | `ai-brand-automator/orchestration/result_handler.py` |
| Pipeline manifest seeder | `ai-brand-automator/orchestration/management/commands/seed_manifests.py` |
| Job executor | `pipeline-orchestrator-svc/app/services/job_executor.py` |
| Pipeline composer | `pipeline-orchestrator-svc/app/nodes/internal/pipeline_composer.py` |
| Node registry | `pipeline-orchestrator-svc/app/factory/node_registry.py` |
| Skill loader + router | `pipeline-orchestrator-svc/app/skills/` |
| Analytics extractors | `ai-brand-automator/analytics/extractors/` |
| OIA models + review API | `ai-brand-automator/apps/onboarding/` |
| Frontend API client | `ai-brand-automator-frontend/src/lib/api.ts` |
| Frontend env config | `ai-brand-automator-frontend/src/lib/env.ts` |
| Tenant context | `ai-brand-automator-frontend/src/contexts/TenantContext.tsx` |

## Key Environment Variables

```bash
# Backend (.env) — via decouple.config()
SECRET_KEY=<required>                        # Fernet encryption key derived from this
GOOGLE_API_KEY=<gemini-key>                  # Omit for mock mode in tests
DATABASE_URL=<neon-postgres-url>
KONG_ENABLED=false                           # true only behind Kong
KAFKA_CONSUMERS_ENABLED=false
ORCHESTRATOR_URL=http://localhost:8010
ORCHESTRATOR_SERVICE_TOKEN=<service-token>
ORCHESTRATOR_CALLBACK_TOKEN=<callback-token>
BACKEND_URL=http://localhost:8001
WORKER_TOKEN=<worker-token>
ORCHESTRATION_KAFKA_ENABLED=false            # true for Kafka dispatch (vs HTTP)

# Frontend (.env.local)
NEXT_PUBLIC_API_URL=http://localhost:8000     # Auto-detected via env.ts in browser
NEXT_PUBLIC_BRAND_EQUITY_API_URL=http://localhost:8090
```

Production domain: `zorven.ai` → frontend, `api.zorven.ai` → backend. Domain mapping is hardcoded in `src/lib/env.ts`, not via env var.

## Redis Database Allocation

DB 0: Django/Celery, DB 1: Orchestrator, DB 2: Discovery + Prompt Cache + OIA (`oia:v1:` prefix), DB 3: Intelligence, DB 4: Titling, DB 5: Content, DB 6: Social, DB 7: RAG Uploader, DB 8: Brand Equity, DB 9: Odoo MCP, DB 10: Odoo Worker, DB 11–15: Market Research/Competitor/Audience/Trend/VoC, DB 16–26: WF2/WF3/WF3.5/POI services.

Requires `databases 27` in redis.conf. **GCP Memorystore** is capped at 16 databases — services ≥ DB 16 map onto **DB 2** with distinct key prefixes (`bpa:`, `baa:`, `bpv:`, `nta:`, `bsa:`, `caa:`, `cga:`, `adpub:`, `coa:`, `ila:`, `poi:`/`prompt:`). Do not reintroduce indices ≥ 16 in GCP deploy scripts.

## Do Not Modify

- `LICENSE`, `docs/LICENSE.md`, `credentials/`, `db.sqlite3` — proprietary, all rights reserved
- `.github/workflows/ci-cd.yml` — CI pipeline (coordinate with team)
- `deployment/config/kong/` — Kong gateway config
- Existing migration files — never edit, always create new ones

## Modify With Caution

- `brand_automator/settings.py` — middleware order is critical
- `brand_automator/middleware.py` — security-sensitive
- `automation/encryption.py` — changes break existing encrypted OAuth tokens
- `conftest.py` — only add fixtures, never remove

## Git Workflow

Two-tier branching: feature branch → PR into `development_main` (dev tier) → PR/sync merge into `main` (production). CI runs on pushes/PRs to `main`, `develop`, `development_main`, and `bugfixes/**`.

Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`

## Testing Boundaries

- **Kafka**: Mocked at import time via `sys.modules` in `conftest.py`
- **Gemini AI**: Falls back to mock data when `GOOGLE_API_KEY` is absent
- **GCS**: Mocked via `unittest.mock.patch`
- **Email**: Redirected to `locmem.EmailBackend` (autouse fixture)
- **Test markers**: `unit`, `integration`, `property`, `hypothesis`, `slow`, `skip_ci`, `gcp`, `asyncio`
- **Test pyramid**: 70% unit / 25% integration / 5% property
