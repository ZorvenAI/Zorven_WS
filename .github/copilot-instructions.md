# AI Brand Automator - Copilot Instructions

> Multi-tenant SaaS for AI-powered brand building. Django + Next.js + Gemini AI + Stripe + Kong Gateway.

## Architecture

```
Frontend (:3000) ──► Kong Gateway (:8000) ──► Django Backend (:8001) ──► PostgreSQL (Neon)
                           │                        │
                    JWT/CORS/Rate-Limit      Gemini 2.0 Flash / Celery+Redis / Stripe
```

**Key directories:**
- `ai-brand-automator/` — Django backend (DRF, JWT, django-tenants multi-tenancy)
- `ai-brand-automator-frontend/` — Next.js 15 + React 19 + TypeScript
- `deployment/docker/kong/` — Kong Gateway DB-less config

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
See pattern usage in: `onboarding/views.py`, `subscriptions/views.py`, `ai_services/views.py`

### Middleware Order (CRITICAL)
In `settings.py`, `CorsMiddleware` **MUST be first** before `DefaultTenantMiddleware`:
```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # FIRST - handles OPTIONS preflight
    "django_tenants.middleware.default.DefaultTenantMiddleware",
    # ...
]
```

### Frontend API Pattern
Always use `apiClient` — handles JWT tokens, 401 auto-refresh, and redirects:
```tsx
import { apiClient } from '@/lib/api';
const data = await apiClient.get('/companies/');  // NOT raw fetch()
```
The API URL auto-detects hostname in browser (`src/lib/env.ts`), so works from localhost or network IP.

### Route Protection
```tsx
import { useAuth } from '@/hooks/useAuth';
export default function ProtectedPage() {
  useAuth();  // Redirects to /auth/login if no token
}
```

## Development Commands

```bash
# Backend (venv is in workspace ROOT)
cd ai-brand-automator && source ../.venv/bin/activate
python manage.py runserver 0.0.0.0:8000

# Frontend
cd ai-brand-automator-frontend && npm run dev

# Tests
pytest -v                    # All 240+ backend tests
pytest -m property           # Hypothesis property tests only
npm test                     # Frontend Jest tests
```

## Testing Patterns

### Test Client Setup (django-tenants requirement)
```python
client = APIClient()
client.defaults["SERVER_NAME"] = "localhost"  # Required for tenant middleware
```

### Property Tests (Hypothesis)
Create **unique tenant per example** to avoid OneToOneField violations:
```python
# In test_properties.py - see onboarding/tests/test_properties.py
def create_test_tenant():
    unique_id = uuid.uuid4().hex[:10]
    tenant = Tenant.objects.create(schema_name=f"test_{unique_id}", ...)
    return tenant

@pytest.mark.property
@given(st.text(min_size=1, max_size=255))
def test_company_name(authenticated_client, name):
    tenant = create_test_tenant()  # Fresh tenant per example
```

### Key Fixtures (`conftest.py`)
- `public_tenant` — Shared public tenant for simple tests
- `authenticated_client` — API client with user + `SERVER_NAME=localhost`
- `authenticated_client_with_tenant` — Adds `_force_tenant` for tenant context

## Key Files

| Purpose | Location |
|---------|----------|
| Django settings | `ai-brand-automator/brand_automator/settings.py` |
| Kong config | `deployment/docker/kong/kong.yaml` |
| Kong middleware | `ai-brand-automator/brand_automator/middleware.py` |
| AI service | `ai-brand-automator/ai_services/services.py` |
| Frontend API client | `ai-brand-automator-frontend/src/lib/api.ts` |
| Test fixtures | `ai-brand-automator/conftest.py` |
| MCP server (23 tools) | `ai-brand-automator/automation/mcp_server.py` |

## Common Gotchas

1. **AI mock mode**: No `GOOGLE_API_KEY` → `GeminiAIService` returns mock data (tests pass without API key)
2. **CORS hostname**: Frontend must use `localhost:3000` (not `127.0.0.1`) to match CORS_ALLOWED_ORIGINS
3. **Stripe redirects**: Use `window.history.replaceState()` after checkout, not `router.replace()`
4. **Social OAuth tokens**: Encrypted in DB via `automation/encryption.py`
5. **Kong proxy check**: Backend verifies `X-Kong-Proxy: true` header before trusting unverified JWT decode

## Environment Variables

```bash
# Backend (.env in ai-brand-automator/)
SECRET_KEY=<required>
GOOGLE_API_KEY=<gemini-api-key>
STRIPE_SECRET_KEY=<stripe-key>
DATABASE_URL=<neon-postgres-url>
KONG_ENABLED=true  # Trust Kong JWT validation

# Frontend (.env.local)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## MCP Server (AI Agent Integration)

```bash
python run_mcp_server.py --transport stdio   # Claude Desktop/VS Code
python run_mcp_server.py --transport sse --port 8003  # Web clients
```
23 tools for social profiles, content scheduling, GBP management. See `automation/README.md`.
