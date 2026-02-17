# AI Brand Automator — Copilot Instructions

> The Brain: loaded first on every Copilot interaction. Keep focused on non-negotiable rules and project identity.

## Project Identity

AI Brand Automator is a **multi-tenant SaaS platform** for AI-powered brand building. Users onboard a company, upload brand assets, and the platform generates brand strategies, manages social media, schedules content, and integrates Google Business Profiles — all powered by Gemini 2.0 Flash.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, TypeScript (strict), Tailwind CSS v4 |
| Backend | Django 4.2, Django REST Framework, SimpleJWT |
| AI | Google Gemini 2.0 Flash (`GeminiAIService` singleton) |
| Database | PostgreSQL (Neon) with `django-tenants` (schema-based multi-tenancy) |
| Gateway | Kong (DB-less): JWT auth, CORS, rate limiting |
| Queue | Celery + Redis (beat scheduler), Apache Kafka (event streaming) |
| Storage | Google Cloud Storage (2 buckets: raw + curated) |
| Payments | Stripe (Basic $29 / Pro $79 / Enterprise $199) |
| Deployment | Railway (Docker), GitHub Actions CI/CD |

## Monorepo Layout

```
ai-brand-automator/           → Django backend (DRF, JWT, django-tenants)
ai-brand-automator-frontend/  → Next.js 15 + React 19 + TypeScript + Tailwind v4
deployment/                   → Docker Compose, Kong config, Railway/k8s manifests
docs/                         → Architecture docs, plans, guides
```

## Non-Negotiable Rules

### Backend

1. **Format**: Black (line-length 88) + Flake8. CI enforces `black --check .` and `flake8 .`
2. **Env vars**: Always `decouple.config()` with defaults and type casts — NEVER `os.environ`
3. **Multi-tenancy**: Always use `getattr(request, 'tenant', None)` — NEVER `request.tenant` directly
4. **Migrations**: Use `migrate_schemas --shared --noinput` — NEVER plain `migrate`
5. **ViewSets**: Use `select_related` on FK querysets, `get_serializer_class()` for action-specific serializers, `perform_create()` for tenant attachment
6. **MIME types**: Always use explicit MIME maps — NEVER rely solely on `mimetypes.guess_type()` (Docker containers lack `/etc/mime.types`)
7. **Encrypted tokens**: OAuth tokens live in `_access_token` columns, exposed via `@property` using `encrypt_token()`/`decrypt_token()`
8. **Pipeline apps** (`data_ingestion/`, `media_curation/`, `rag_index/`): Use **Hexagonal Architecture** — Pydantic domain models (NOT Django ORM), ABC ports, concrete adapters
9. **Test client**: Always set `client.defaults["SERVER_NAME"] = "localhost"` for tenant middleware

### Frontend

1. **API calls**: Always use `apiClient` from `@/lib/api` — NEVER raw `fetch()`
2. **Route protection**: Always call `useAuth()` hook in protected pages
3. **TypeScript**: Strict mode, path alias `@/* → ./src/*`
4. **Formatting**: ESLint only (no Prettier). Config in `eslint.config.mjs`
5. **Icons**: Prefer `lucide-react`
6. **Components**: Functional components only, no class-based React
7. **Design system**: "Digital Twilight" dark theme — use `glass-card`, `bg-brand-midnight`, `text-brand-electric`, `text-brand-silver` classes. See `DESIGN_SYSTEM.md`
8. **Hydration safety**: Components using `useTenantRole()` or `TenantContext` (localStorage-backed) MUST guard with `hasMounted` before rendering role-dependent JSX:
```tsx
const [hasMounted, setHasMounted] = useState(false);
useEffect(() => setHasMounted(true), []);
if (!hasMounted) return <LoadingSpinner />;
// ... role-dependent JSX below
```

### Security

1. **Input sanitization**: Use `sanitize_text_input()`, `sanitize_ai_prompt()`, `validate_file_upload()` from `validators.py`
2. **Kong proxy check**: Backend verifies `X-Kong-Proxy: true` header. Only enable `KONG_ENABLED=true` behind Kong
3. **DB SSL**: `sslmode=require`, `channel_binding=require` for Neon

## Critical Code Patterns

### Multi-Tenancy Defensive Access
```python
from django.db.models import Q

# ✅ CORRECT — Query (backward-compatible with pre-tenant data)
tenant = getattr(request, 'tenant', None)
qs = Model.objects.filter(Q(tenant=tenant) | Q(tenant__isnull=True))

# ✅ CORRECT — Create (always attach tenant)
obj = Model.objects.create(
    user=request.user,
    tenant=getattr(request, 'tenant', None),
    ...
)

# ❌ WRONG — AttributeError in tests
tenant = request.tenant

# ❌ WRONG — Excludes pre-tenant data
qs = Model.objects.filter(tenant=tenant) if tenant else Model.objects.filter(tenant__isnull=True)
```

### Middleware Order (CRITICAL)
```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",               # FIRST
    "django_tenants.middleware.default.DefaultTenantMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # ... standard Django ...
    "brand_automator.middleware.KongAuthenticationMiddleware",  # After AuthenticationMiddleware
    "brand_automator.middleware.SecurityMiddleware",
    "brand_automator.middleware.RequestValidationMiddleware",
    "brand_automator.middleware.RateLimitMiddleware",
]
```

### Frontend API Client
```tsx
import { apiClient } from '@/lib/api';
const data = await apiClient.get('/companies/');
// apiClient.upload() omits Content-Type for multipart boundary
// 409 → DuplicateFileError from @/lib/errors.ts
```

### File Upload Deduplication
Backend: `UniqueConstraint(fields=["tenant", "company", "file_name"])` on `BrandAsset`. Returns HTTP 409 with existing asset info. Frontend catches via `DuplicateFileError`, shows replace dialog.

## Key Files Reference

| Purpose | Path |
|---------|------|
| Django settings | `ai-brand-automator/brand_automator/settings.py` |
| URL routing | `ai-brand-automator/brand_automator/urls.py` |
| Custom auth | `ai-brand-automator/brand_automator/auth_views.py` |
| Input validation | `ai-brand-automator/brand_automator/validators.py` |
| Middleware | `ai-brand-automator/brand_automator/middleware.py` |
| AI service | `ai-brand-automator/ai_services/services.py` |
| Pipeline service | `ai-brand-automator/onboarding/services.py` |
| Encryption | `ai-brand-automator/automation/encryption.py` |
| MCP server | `ai-brand-automator/automation/mcp_server.py` |
| Frontend API | `ai-brand-automator-frontend/src/lib/api.ts` |
| Frontend env | `ai-brand-automator-frontend/src/lib/env.ts` |
| Frontend errors | `ai-brand-automator-frontend/src/lib/errors.ts` |
| Test fixtures | `ai-brand-automator/conftest.py` |
| Design system | `ai-brand-automator-frontend/DESIGN_SYSTEM.md` |
| Tenant context | `ai-brand-automator-frontend/src/contexts/TenantContext.tsx` |
| Tenant hooks | `ai-brand-automator-frontend/src/hooks/useTenantRole.ts` |
| Architecture | `ARCHITECTURE.md` |

## Build & Run

```bash
# Backend
cd ai-brand-automator && source ../.venv/bin/activate
python manage.py runserver 0.0.0.0:8000

# Frontend
cd ai-brand-automator-frontend && npm run dev

# Full stack
cd deployment && docker compose up

# Tests
cd ai-brand-automator && pytest -v          # 1890+ backend tests
cd ai-brand-automator-frontend && npm test  # Jest (60% coverage threshold)

# Format & lint
cd ai-brand-automator && black . && flake8 .
cd ai-brand-automator-frontend && npm run lint
```

## Environment Variables

```bash
# Backend (.env) — via decouple.config()
SECRET_KEY=<required>                        # Fernet encryption key derived from this
GOOGLE_API_KEY=<gemini-key>                  # Omit for mock mode
STRIPE_SECRET_KEY=<stripe-key>
DATABASE_URL=<neon-postgres-url>
KONG_ENABLED=false                           # true only behind Kong
KAFKA_CONSUMERS_ENABLED=false                # true for Kafka pipeline

# Frontend (.env.local)
NEXT_PUBLIC_API_URL=http://localhost:8000     # Auto-detected via env.ts in browser
```
