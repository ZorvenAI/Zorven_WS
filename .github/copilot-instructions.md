# AI Brand Automator - Copilot Instructions

> Multi-tenant SaaS for AI-powered brand building. Django + Next.js + Gemini AI + Stripe + Kong Gateway.

## Architecture

```
Frontend (:3000) ──► Kong Gateway (:8000) ──► Django Backend (:8001) ──► PostgreSQL (Neon)
                           │                        │
                    JWT/CORS/Rate-Limit      Gemini 2.0 Flash / Celery+Redis / Stripe
                                                    │
                                     Kafka ──► Ingestion ──► Curation ──► RAG Index
```

**Monorepo layout:**
- `ai-brand-automator/` — Django backend (DRF, JWT, django-tenants)
- `ai-brand-automator-frontend/` — Next.js 15 + React 19 + TypeScript + Tailwind v4
- `deployment/` — Docker Compose, Kong config, Railway/k8s manifests

**Data pipeline apps** use **Hexagonal Architecture** (Ports & Adapters):
- `data_ingestion/` and `media_curation/` — Domain models are **Pydantic BaseModel**, NOT Django ORM. Ports are ABCs, adapters implement them. See `data_ingestion/ports/`, `media_curation/adapters/`.
- Pipeline flow: `Upload → Kafka(raw-ingestion) → IngestionService → Kafka(curation-needed) → CurationService → Kafka(rag-sync-ready) → RAG Index`

## Code Style

### Backend
- **Black** (line-length 88, py311/py312) — CI runs `black --check .`
- **Flake8** (max-line-length 88, ignores E203/W503/F403/F405) — see `setup.cfg`
- **Env vars** via `decouple.config()` (NOT `os.environ`) — always provide defaults and type casts
- Config: `pyproject.toml` (black), `setup.cfg` (flake8), `pytest.ini` (pytest)

### Frontend
- **ESLint** flat config (`eslint.config.mjs`) — `next/core-web-vitals` + `next/typescript`
- **TypeScript strict mode** — path alias `@/* → ./src/*`
- **No Prettier** — formatting is ESLint-only
- CI: `npm run lint && npx tsc --noEmit && npm run build && npm test`

## Critical Patterns (MUST FOLLOW)

### Multi-Tenancy Defensive Access
All models have **nullable `tenant` FK**. Never access `request.tenant` directly:
```python
# ✅ CORRECT - in every ViewSet/view
tenant = getattr(request, 'tenant', None)
queryset = Model.objects.filter(tenant=tenant) if tenant else Model.objects.filter(tenant__isnull=True)

# ❌ WRONG - AttributeError in tests/non-tenant contexts
tenant = request.tenant
```
Most apps are `SHARED_APPS` (public schema). Only `files` uses per-tenant schemas. See `settings.py` SHARED_APPS/TENANT_APPS.

### Middleware Order (CRITICAL)
In `settings.py`, `CorsMiddleware` **MUST be first**, then custom security middlewares AFTER `AuthenticationMiddleware`:
```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",               # FIRST
    "django_tenants.middleware.default.DefaultTenantMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",           # After SecurityMiddleware
    # ... standard Django ...
    "brand_automator.middleware.KongAuthenticationMiddleware",  # After AuthenticationMiddleware
    "brand_automator.middleware.SecurityMiddleware",            # Custom security headers
    "brand_automator.middleware.RequestValidationMiddleware",   # Injection detection
    "brand_automator.middleware.RateLimitMiddleware",
]
```

### Frontend API Pattern
Always use `apiClient` — handles JWT tokens, 401 auto-refresh with request queuing, and redirects:
```tsx
import { apiClient } from '@/lib/api';
const data = await apiClient.get('/companies/');  // NOT raw fetch()
```
- `apiClient.upload()` omits `Content-Type` so browser sets multipart boundary
- 409 responses throw `DuplicateFileError` (from `@/lib/errors.ts`) with existing asset metadata
- API URL auto-detects hostname in browser via `src/lib/env.ts` — works from localhost or network IP

### Route Protection
```tsx
import { useAuth } from '@/hooks/useAuth';
export default function ProtectedPage() {
  useAuth();  // Redirects to /auth/login if no token
}
```

### File Upload Deduplication
Backend enforces `UniqueConstraint(fields=["tenant", "company", "file_name"])` on `BrandAsset`. Upload endpoint returns HTTP 409 with existing asset info. Frontend catches via `DuplicateFileError` and shows replace confirmation dialog. On replacement: old GCS blob is deleted, `pipeline_trace_id` is reset.

### MIME Type Handling
Docker containers lack `/etc/mime.types`. Always use explicit MIME maps (see `_EXTENSION_MIME_MAP` in `onboarding/services.py` and `_guess_mime_type()` in `media_curation/adapters/document_processor.py`) — never rely solely on `mimetypes.guess_type()`.

### Encrypted Token Storage
`SocialProfile` model stores OAuth tokens in `_access_token` (underscore-prefixed) DB columns exposed via `@property` getters/setters calling `encrypt_token()`/`decrypt_token()` from `automation/encryption.py`.

## Build & Development

```bash
# Backend (venv is in workspace ROOT, not inside ai-brand-automator/)
cd ai-brand-automator && source ../.venv/bin/activate
python manage.py runserver 0.0.0.0:8000

# Frontend
cd ai-brand-automator-frontend && npm run dev

# Full stack (Docker)
cd deployment && docker compose up    # Kong:8000, Backend:8001, Frontend:3000

# Format & lint
cd ai-brand-automator && black . && flake8 .
cd ai-brand-automator-frontend && npm run lint
```

### Migrations
```bash
python manage.py makemigrations
python manage.py migrate_schemas --shared --noinput   # NOT plain 'migrate' — django-tenants requires this
```

## Testing

```bash
pytest -v                    # All 240+ backend tests
pytest -m property           # Hypothesis property tests only
pytest -m "not slow"         # Skip slow tests
npm test                     # Frontend Jest tests (60% coverage threshold)
```

### Test Infrastructure (conftest.py)
- **Kafka mocked at import time** — `confluent_kafka` replaced with `MagicMock` in `sys.modules` BEFORE Django imports. Tests never connect to real Kafka.
- **GeminiAIService mock mode** — No `GOOGLE_API_KEY` → returns fallback data. Tests pass without API key.
- **Email mocked** (autouse) — `locmem.EmailBackend`

### Test Client Setup (django-tenants requirement)
```python
client = APIClient()
client.defaults["SERVER_NAME"] = "localhost"  # REQUIRED for tenant middleware
```

### Key Fixtures
| Fixture | Scope | Purpose |
|---------|-------|---------|
| `setup_public_tenant` | session | Creates public tenant with `localhost` domain |
| `api_client` | function | APIClient with `SERVER_NAME=localhost` |
| `authenticated_client` | function | `force_authenticate(user)` + SERVER_NAME |
| `authenticated_client_with_tenant` | function | Also sets `handler._force_tenant` for tenant context |
| `unique_tenant` | function | UUID-based tenant — essential for Hypothesis |
| `shared_tenant` | module | Shared tenant for read-only tests (faster) |
| `mock_gemini_api` | function | Mocks Gemini AI responses |
| `mock_gcs_upload` / `mock_gcs_delete` | function | Mocks GCS operations |

### Hypothesis Property Tests
Create **unique tenant per example** to avoid OneToOneField violations:
```python
def create_test_tenant():
    unique_id = uuid.uuid4().hex[:10]
    tenant = Tenant.objects.create(schema_name=f"test_{unique_id}", ...)
    return tenant

@pytest.mark.property
@property_settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=10, deadline=None)
@given(st.text(min_size=1, max_size=255))
def test_company_name(authenticated_client, name):
    tenant = create_test_tenant()  # Fresh tenant per example — NOT via fixture
```

### Frontend Tests
- Jest + `jest-environment-jsdom`, path alias `@/ → <rootDir>/src/`
- Coverage thresholds: 60% branches/functions/lines/statements

## Key Files

| Purpose | Location |
|---------|----------|
| Django settings | `ai-brand-automator/brand_automator/settings.py` |
| URL routing | `ai-brand-automator/brand_automator/urls.py` (all under `/api/v1/`) |
| Custom auth (email login) | `ai-brand-automator/brand_automator/auth_views.py` |
| Input validation/sanitization | `ai-brand-automator/brand_automator/validators.py` |
| Kong middleware | `ai-brand-automator/brand_automator/middleware.py` |
| AI service | `ai-brand-automator/ai_services/services.py` |
| Pipeline service | `ai-brand-automator/onboarding/services.py` |
| Frontend API client | `ai-brand-automator-frontend/src/lib/api.ts` |
| Frontend env config | `ai-brand-automator-frontend/src/lib/env.ts` |
| Frontend error types | `ai-brand-automator-frontend/src/lib/errors.ts` |
| Test fixtures | `ai-brand-automator/conftest.py` |
| MCP server | `ai-brand-automator/automation/mcp_server.py` |

## Project Conventions

### Backend API Pattern
- ViewSets with `select_related` on querysets for FK performance
- `get_serializer_class()` returns different serializers for `create`, `update`, `default`
- `perform_create()` attaches tenant with fallback to public tenant
- `@action(detail=True, methods=["post"])` for model-specific operations
- IntegrityError handling wraps `create()` calls for unique constraints

### Pipeline Service Pattern
- Singleton via `get_pipeline_service()` module-level function
- Lazy-loaded Kafka producer (`@property` with `None`-check)
- Graceful degradation: Kafka unavailable → marks asset as "ingested" synchronously
- Smart retry routing: `retry_asset_pipeline()` checks GCS path prefix to determine retry stage

### Frontend Component Organization
```
src/components/{feature}/     — Feature-specific components
src/hooks/                    — Custom hooks (useAuth, useAssets, useFileFilters, usePagination)
src/lib/                      — Utilities (api.ts, env.ts, errors.ts)
src/types/                    — Shared TypeScript types
src/app/{route}/page.tsx      — All pages use 'use client' directive
```

### Design System
"Digital Twilight" dark theme — custom CSS classes: `bg-brand-midnight`, `bg-brand-dark`, `text-brand-electric`, `text-brand-silver`, `glass-card`, `aura-glow`. See `DESIGN_SYSTEM.md`.

## Security

- **Kong proxy check**: Backend verifies `X-Kong-Proxy: true` before trusting unverified JWT. Only enable `KONG_ENABLED=true` when backend is network-isolated behind Kong.
- **Input sanitization**: `validators.py` — `sanitize_text_input()` (bleach), `sanitize_ai_prompt()` (prompt injection regex), `validate_file_upload()` (MIME/extension/path-traversal checks)
- **Rate limiting**: In-memory `RateLimitMiddleware` in custom middleware chain
- **OAuth tokens**: Encrypted at rest (AES via `automation/encryption.py`)
- **DB SSL**: `sslmode=require`, `channel_binding=require` for Neon Serverless

## Deployment

- **Railway**: `railway.json` in `ai-brand-automator/` — set Root Directory to `ai-brand-automator` in Railway dashboard (no leading/trailing slash)
- **Docker Compose**: `deployment/docker-compose.yml` — Backend only accessible through Kong's Docker network
- **Procfile**: 8 process types (web, worker, beat, ingestion-worker/consumer, curation-worker/consumer, rag-index-consumer)
- **CI**: `.github/workflows/ci-cd.yml` — 4 jobs: backend-tests (Postgres), media-curation (Postgres+Redis), frontend, build-images (main/develop only)

## Environment Variables

```bash
# Backend (.env in ai-brand-automator/) — accessed via decouple.config()
SECRET_KEY=<required>
GOOGLE_API_KEY=<gemini-key>          # Omit for mock mode in dev/tests
STRIPE_SECRET_KEY=<stripe-key>
DATABASE_URL=<neon-postgres-url>
KONG_ENABLED=false                    # true only in production behind Kong
KAFKA_CONSUMERS_ENABLED=false         # true to enable Celery beat Kafka tasks

# Frontend (.env.local)
NEXT_PUBLIC_API_URL=http://localhost:8000    # Overridden by env.ts hostname detection in browser
```

## MCP Server (AI Agent Integration)

```bash
python run_mcp_server.py --transport stdio   # Claude Desktop/VS Code
python run_mcp_server.py --transport sse --port 8003  # Web clients
```
23 tools for social profiles, content scheduling, GBP management. See `automation/README.md`.
