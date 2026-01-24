# AI Brand Automator - Copilot Instructions

> Multi-tenant SaaS for AI-powered brand building. Django + Next.js + Gemini AI + Stripe + Kong Gateway.

## Architecture at a Glance

```
                    ┌─── Kong Gateway (:8000) ───┐
Frontend (:3000) ──►│  JWT Auth │ CORS │ Rate   │──► Django Backend (:8001)
                    │  Limiting │      │ Limit  │         ↓
                    └────────────────────────────┘   PostgreSQL (Neon)
                              │                           ↓
                              ▼                     Gemini 2.0 Flash
                         GCS Direct              Stripe / Celery+Redis
                         (file uploads)
```

**Key directories:**
- `ai-brand-automator/` - Django backend (DRF, JWT auth, multi-tenancy)
- `ai-brand-automator-frontend/` - Next.js 15 + React 19 + TypeScript
- `deployment/docker/kong/` - Kong Gateway configuration
- `deployment/` - Docker, Railway configs

## Kong Gateway Integration

**Ports when Kong enabled:**
| Service | Port | Access |
|---------|------|--------|
| Kong Gateway | 8000 | External entry point |
| Django Backend | 8001 | Internal only (via Kong) |
| Kong Admin API | 8002 | Debug/config |
| MCP Server | 8003 | AI agent tools |
| Frontend | 3000 | Direct |

**Key settings:**
```python
# settings.py - when Kong handles auth
KONG_ENABLED = True  # Trust Kong JWT validation, skip Django verification
```

**Key files:**
- [deployment/docker/kong/kong.yaml](deployment/docker/kong/kong.yaml) - Kong declarative config
- [brand_automator/middleware.py](ai-brand-automator/brand_automator/middleware.py) - `KongAuthenticationMiddleware`

**Start with Kong:**
```bash
cd ai-brand-automator
docker-compose up -d  # Starts Kong, Django, Redis, Postgres
# Frontend points to Kong at localhost:8000
```

## Critical Patterns

### ⚠️ Multi-Tenancy Defensive Access
Models have nullable `tenant` FK. **Always use**:
```python
tenant = getattr(request, 'tenant', None)  # NOT request.tenant
queryset = Model.objects.filter(tenant=tenant) if tenant else Model.objects.filter(tenant__isnull=True)
```

### Middleware Order (CRITICAL)
`CorsMiddleware` MUST be first in MIDDLEWARE, before `TenantMainMiddleware`.

### Frontend API Pattern
Use `apiClient` from `src/lib/api.ts` - handles auth tokens and 401 refresh automatically.
```tsx
import { apiClient } from '@/lib/api';
const data = await apiClient.get('/companies/');  // NOT raw fetch
```

### Route Protection
```tsx
import { useAuth } from '@/hooks/useAuth';
export default function ProtectedPage() {
  useAuth();  // Redirects to /auth/login if no token
  // ...
}
```

## Development Commands

```bash
# Backend (venv is in workspace ROOT, not ai-brand-automator/)
cd ai-brand-automator && source ../.venv/bin/activate
python manage.py runserver                # → localhost:8000

# Frontend
cd ai-brand-automator-frontend && npm run dev  # → localhost:3000

# Tests
pytest -v                                 # Backend (226+ tests)
pytest -m property                        # Hypothesis property tests
npm test                                  # Frontend (Jest)
```

## API Endpoints Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/register/` | POST | Create account (email/username/password) |
| `/api/v1/auth/login/` | POST | Login (email/password → JWT) |
| `/api/v1/companies/` | CRUD | Company management |
| `/api/v1/companies/{id}/generate_brand_strategy/` | POST | AI brand generation |
| `/api/v1/automation/` | CRUD | Social media automation |
| `/api/v1/subscriptions/` | CRUD | Stripe subscriptions |

## Key Files

| Purpose | Location |
|---------|----------|
| Django settings | [ai-brand-automator/brand_automator/settings.py](ai-brand-automator/brand_automator/settings.py) |
| Kong config | [deployment/docker/kong/kong.yaml](deployment/docker/kong/kong.yaml) |
| Kong middleware | [ai-brand-automator/brand_automator/middleware.py](ai-brand-automator/brand_automator/middleware.py) |
| AI service (Gemini) | [ai-brand-automator/ai_services/services.py](ai-brand-automator/ai_services/services.py) |
| Frontend API client | [ai-brand-automator-frontend/src/lib/api.ts](ai-brand-automator-frontend/src/lib/api.ts) |
| Test fixtures | [ai-brand-automator/conftest.py](ai-brand-automator/conftest.py) |
| MCP server (23 tools) | [ai-brand-automator/automation/mcp_server.py](ai-brand-automator/automation/mcp_server.py) |

## Testing Patterns

- **Test client requires**: `client.defaults["SERVER_NAME"] = "localhost"` (django-tenants)
- **Property tests**: Use Hypothesis in `**/test_properties.py`
- **Fixtures**: Public tenant auto-created in `conftest.py`

## Common Gotchas

1. **AI mock mode**: If `GOOGLE_API_KEY` not set, `GeminiAIService` returns mock data
2. **CORS**: Frontend must use `localhost:3000` (not 127.0.0.1)
3. **Stripe sync**: Use `window.history.replaceState()` after checkout, not `router.replace()`
4. **Social OAuth**: Tokens encrypted in DB via `automation/encryption.py`

## Environment Variables

```bash
# Backend (.env)
SECRET_KEY=<required>
GOOGLE_API_KEY=<gemini>
STRIPE_SECRET_KEY=<stripe>
DATABASE_URL=<neon-postgres-url>

# Frontend (.env.local)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## MCP Server (AI Agent Integration)

```bash
python run_mcp_server.py --transport stdio  # For Claude Desktop/VS Code
python run_mcp_server.py --transport sse --port 8001  # For web clients
```

23 tools for social media automation, content scheduling, GBP management. See [automation/README.md](ai-brand-automator/automation/README.md).
