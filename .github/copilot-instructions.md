# AI Brand Automator - Copilot Instructions

## Project Overview

**Multi-tenant SaaS platform** for AI-powered brand building with Django + Next.js:
- **Backend**: Django 4.2 + DRF at `ai-brand-automator/` (port 8000)
- **Frontend**: Next.js 15 + React 19 + TypeScript at `ai-brand-automator-frontend/` (port 3000) 
- **Database**: PostgreSQL (Neon hosted) - multi-tenancy PARTIALLY DISABLED for MVP
- **AI**: Google Gemini 2.0 Flash for brand strategy generation
- **Payments**: Stripe for subscription management

**🚨 CRITICAL STATE**: Multi-tenancy configured with `django-tenants` but in transitional MVP mode. Models have nullable `tenant` FK. Always use defensive access: `tenant = getattr(request, 'tenant', None)` in views.

## Essential Architecture

### Critical Data Flow
1. User registers via `POST /api/v1/auth/register/` (email-based auth)
2. Login with `POST /api/v1/auth/login/` (email + password → JWT tokens)
3. Create `Company` via `POST /api/v1/companies/` (auto-creates `OnboardingProgress`)
4. Generate AI strategy with `POST /api/v1/companies/{id}/generate_brand_strategy/`
5. `GeminiAIService.generate_brand_strategy()` creates vision/mission/values

### Django App Structure (SHARED vs TENANT)
- **SHARED_APPS**: `tenants`, `ai_services` (available in all schemas)
- **TENANT_APPS**: `onboarding`, `files`, `automation` (isolated per tenant, but nullable tenant FK for MVP)

### URL Routing Structure
- **Auth**: `/api/v1/auth/{register,login,refresh}/` - Email-based JWT auth in [brand_automator/urls.py](ai-brand-automator/brand_automator/urls.py)
- **Onboarding**: `/api/v1/companies/` (ViewSet) - [onboarding/urls.py](ai-brand-automator/onboarding/urls.py)
- **AI Services**: `/api/v1/ai/` - [ai_services/urls.py](ai-brand-automator/ai_services/urls.py)
- **Subscriptions**: `/api/v1/subscriptions/` - [subscriptions/urls.py](ai-brand-automator/subscriptions/urls.py)
- **Health**: `/health/`, `/ready/`, `/alive/` - Non-auth monitoring endpoints

## Development Workflows

### Starting Services (Required Order)
```bash
# Backend - Virtual env is ONE LEVEL UP from ai-brand-automator/
cd ai-brand-automator
source ../.venv/bin/activate  # ⚠️ .venv is in workspace root
python manage.py runserver     # → http://localhost:8000

# For network/mobile testing (accessible from other devices):
python manage.py runserver 0.0.0.0:8000  # → http://<your-ip>:8000

# Frontend - Separate terminal
cd ai-brand-automator-frontend  
npm run dev                    # → http://localhost:3000

# For network/mobile testing:
npm run dev -- -H 0.0.0.0      # → http://<your-ip>:3000
```

### Mobile/Network Testing Setup
When testing from mobile devices or other machines on the network:
1. Get your IP: `ipconfig getifaddr en0` (macOS)
2. Add IP to tenant domains in database (see Common Issues section)
3. Update frontend `.env.local`: `NEXT_PUBLIC_API_URL=http://<your-ip>:8000`
4. Run servers with `0.0.0.0` binding

### Testing

**Backend** (pytest + Hypothesis property-based testing):
```bash
cd ai-brand-automator
source ../.venv/bin/activate
pytest -v                      # All tests
pytest -m unit                 # Unit tests only
pytest -m property             # Property-based tests
pytest --hypothesis-show-statistics  # Hypothesis stats

# Automation service tests (149 tests)
pytest automation/tests/ -v    # All automation tests
pytest automation/tests/test_models.py -v       # 51 unit tests
pytest automation/tests/test_properties.py -v   # 18 property tests
pytest automation/tests/test_integration.py -v  # 26 integration tests
pytest automation/tests/test_services.py -v     # 36 service tests
```

- **Test fixtures**: [conftest.py](ai-brand-automator/conftest.py) - Public tenant auto-created, schema reset after each test
- **Property tests**: [onboarding/tests/test_properties.py](ai-brand-automator/onboarding/tests/test_properties.py) - Hypothesis generates random data to test invariants
- **Automation tests**: [automation/tests/](ai-brand-automator/automation/tests/) - Comprehensive test suite (models, properties, integration, services)
- **Key pattern**: `@pytest.fixture` with `SERVER_NAME='localhost'` for django-tenants compatibility

**Frontend** (Jest + React Testing Library):
```bash
cd ai-brand-automator-frontend
npm test                       # Run tests
npm test -- --coverage         # With coverage (60% threshold)
```

- Test files: `__tests__/**/*.test.tsx` or `*.test.tsx` anywhere
- Path aliases: `@/` → `src/` (configured in jest.config.js and tsconfig.json)

### Database Operations
```bash
# Standard Django (multi-tenancy disabled for migrations)
python manage.py makemigrations
python manage.py migrate

# ⚠️ Multi-tenancy note: Currently using standard migrations
# If full multi-tenancy enabled, use: migrate_schemas --shared
```

### Environment Setup
```bash
# Backend (.env at ai-brand-automator/.env):
SECRET_KEY=<django-secret>
GOOGLE_API_KEY=<gemini-api-key>
DEBUG=True
DB_NAME=<neon-db>
DB_USER=<neon-user>
DB_PASSWORD=<neon-pass>
DB_HOST=<host>.neon.tech
DB_PORT=5432

# Frontend (.env.local):
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Project-Specific Patterns

### Django ViewSets & Custom Actions
AI generation endpoints use `@action(detail=True, methods=['post'])`:
```python
# Pattern in onboarding/views.py
@action(detail=True, methods=['post'])
def generate_brand_strategy(self, request, pk=None):
    company = self.get_object()
    ai_result = ai_service.generate_brand_strategy(company_data)
    company.vision_statement = ai_result['vision_statement']
    company.save()
```

### AI Service Integration
- `ai_services/services.py` exports singleton `ai_service = GeminiAIService()`
- Uses **Gemini 2.0 Flash** model (updated from deprecated 1.5)
- Always logs generations to `AIGeneration` model with tokens/processing time
- Fallback responses if `GOOGLE_API_KEY` not configured (returns mock data)
- Response parsing extracts sections like "Vision Statement", "Mission Statement" from AI text
- Color palette format expected: `Primary: #HEXCODE, Secondary: #HEXCODE, Accent: #HEXCODE`

### Frontend API Client
- Centralized in `src/lib/api.ts` with auto token injection
- Auto-redirects to `/auth/login` on 401 responses
- Always use `apiClient.get|post|put()` instead of raw fetch
- Token refresh mechanism: uses `refresh_token` from localStorage when `access_token` expires

### Frontend Route Protection
- `useAuth()` hook in [src/hooks/useAuth.ts](ai-brand-automator-frontend/src/hooks/useAuth.ts) checks for `access_token` in localStorage
- Client-side only (no SSR token validation)
- Pattern: Call `useAuth()` at top of protected page components
```tsx
export default function ProtectedPage() {
  useAuth(); // Redirects to login if no token
  // ... component code
}
```

### Multi-Tenancy Defensive Pattern
⚠️ **CRITICAL**: Models expect tenant but middleware is partially disabled
```python
# Always use this pattern in views:
tenant = getattr(request, 'tenant', None)
if tenant:
    queryset = Model.objects.filter(tenant=tenant)
else:
    # MVP mode - no tenant filtering
    queryset = Model.objects.filter(tenant__isnull=True)
```

## Common Issues & Solutions

### Multi-Tenancy Access Errors
When seeing `'WSGIRequest' object has no attribute 'tenant'` - middleware is enabled but broken:
```python
# Fix: Replace request.tenant with defensive access
tenant = getattr(request, 'tenant', None)
# Then handle both cases appropriately
```

### AI Service Failures
`GeminiAIService` returns mock data if `GOOGLE_API_KEY` not set. Check logs for:
```python
# Always returns dict even on error - look for "Based on..." fallback text
result = {'vision_statement': "Based on technology industry..."}
```

### CORS Issues
Frontend must run on **localhost:3000** (NOT 127.0.0.1) to match `CORS_ALLOWED_ORIGINS`.

**⚠️ CRITICAL**: `CorsMiddleware` MUST be first in MIDDLEWARE list (before `TenantMainMiddleware`) to handle OPTIONS preflight requests properly.

### Network/Mobile Access Issues
When accessing from network IP (mobile testing), you must add the IP to tenant domains:
```python
# Run in Django shell or script:
from tenants.models import Tenant, Domain
tenant = Tenant.objects.get(schema_name='public')
Domain.objects.get_or_create(domain='<your-ip>', defaults={'tenant': tenant, 'is_primary': False})
```

### Authentication Flow
- Registration: `POST /api/v1/auth/register/` (email/username/password)
- Login: `POST /api/v1/auth/login/` (email/password → JWT tokens)
- Frontend stores tokens in localStorage, auto-refreshes on 401

## Key File Locations

- **Settings**: [ai-brand-automator/brand_automator/settings.py](ai-brand-automator/brand_automator/settings.py#L37-L56) - Multi-tenancy toggle
- **AI Service**: [ai-brand-automator/ai_services/services.py](ai-brand-automator/ai_services/services.py) - Gemini integration
- **API Client**: [ai-brand-automator-frontend/src/lib/api.ts](ai-brand-automator-frontend/src/lib/api.ts) - Frontend HTTP client
- **Issue Tracker**: [docs/CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](docs/CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md) - 63 known issues

## Current Status & Issues

**Status**: Phase 4 complete - Stripe integration working

**Completed Phases**:
- ✅ Phase 1: Foundation (Django multi-tenancy, PostgreSQL, auth)
- ✅ Phase 2: Core Backend (Onboarding APIs, GCS integration, AI services)
- ✅ Phase 3: Frontend Development (Next.js, auth UI, onboarding flow, chat)
- ✅ Phase 4: Stripe Integration (subscriptions, checkout, sync)

**Major Resolved Issues**:
- ✅ Email-based login working
- ✅ Company creation with nullable tenant field  
- ✅ Defensive tenant access in views
- ✅ Comprehensive test suite (pytest + Hypothesis property tests)
- ✅ CORS middleware order fixed (must be before TenantMainMiddleware)
- ✅ Network/mobile testing with tenant domain registration
- ✅ Gemini 2.0 Flash model integration (1.5 deprecated)
- ✅ Subscription sync after Stripe checkout

---

## Phase 4: Integrations - COMPLETED

### 4.1 Stripe Payment Integration ✅

**Implemented:**
- `subscriptions` Django app with models: `Subscription`, `SubscriptionPlan`, `PaymentHistory`
- `stripe_customer_id` and `subscription_status` fields on Tenant model
- Stripe checkout session creation and redirect
- Subscription sync endpoint for post-checkout updates
- Webhook handler for Stripe events

**API Endpoints:**
- `GET /api/v1/subscriptions/plans/` - List available plans
- `GET /api/v1/subscriptions/status/` - Current subscription status
- `POST /api/v1/subscriptions/create-checkout-session/` - Create Stripe checkout
- `POST /api/v1/subscriptions/sync/` - Sync subscription from Stripe
- `POST /api/v1/subscriptions/webhook/` - Handle Stripe webhooks
- `POST /api/v1/subscriptions/create-portal-session/` - Customer billing portal
- `POST /api/v1/subscriptions/cancel/` - Cancel subscription

**Subscription Tiers:**
   | Plan | Price | Features |
   |------|-------|----------|
   | Basic | $29/mo | Core features, 1 brand |
   | Pro | $79/mo | Advanced AI, 5 brands, automation |
   | Enterprise | $199/mo | Unlimited, team features |

**Frontend Implementation:**
- `/subscription` page with plan cards and checkout flow
- `SubscriptionStatus` component shows current plan
- Post-checkout sync using `window.history.replaceState()` to avoid race conditions

**Environment Variables:**
```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_BASIC=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_ENTERPRISE=price_...
```

### 4.2 Automation Models (Priority: MEDIUM)

**Backend Tasks:**
1. **Populate `automation` app with models:**
   - `SocialProfile` - Connected social accounts
   - `AutomationTask` - Scheduled automation jobs
   - `ContentCalendar` - Scheduled posts

2. **API Endpoints:**
   - `GET /api/v1/automation/social-profiles` - List connected profiles
   - `POST /api/v1/automation/connect/{platform}` - OAuth connect (stub)
   - `DELETE /api/v1/automation/disconnect/{platform}` - Disconnect

3. **Supported Platforms (MVP):**
   - LinkedIn (Company Pages API)
   - Twitter/X (OAuth 2.0)
   - Instagram Business (via Facebook Graph API)

**Frontend Tasks:**
1. Create `/automation` page
2. Add social connection buttons
3. Show connected accounts status

### 4.3 Webhook Handling (Priority: HIGH)

**Stripe webhook events to handle:**
- `checkout.session.completed` - New subscription
- `invoice.payment_succeeded` - Recurring payment
- `invoice.payment_failed` - Payment failure
- `customer.subscription.updated` - Plan change
- `customer.subscription.deleted` - Cancellation

### 4.4 Files to Create/Modify

**New Files:**
```
ai-brand-automator/
├── subscriptions/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py          # Subscription, Plan, PaymentHistory
│   ├── serializers.py
│   ├── views.py           # Checkout, webhook, portal
│   ├── urls.py
│   └── services.py        # Stripe service wrapper
├── automation/
│   ├── models.py          # SocialProfile, AutomationTask, ContentCalendar
│   ├── serializers.py
│   ├── views.py
│   └── urls.py

ai-brand-automator-frontend/src/
├── app/
│   ├── subscription/
│   │   └── page.tsx       # Pricing/plans page
│   ├── billing/
│   │   └── page.tsx       # Billing management
│   └── automation/
│       └── page.tsx       # Social connections
├── components/
│   ├── subscription/
│   │   ├── PlanCard.tsx
│   │   └── CheckoutButton.tsx
│   └── automation/
│       └── SocialConnectButton.tsx
```

**Modified Files:**
- `tenants/models.py` - Add `stripe_customer_id` field
- `brand_automator/urls.py` - Add subscription/automation routes
- `brand_automator/settings.py` - Add Stripe config

### Implementation Order

| Step | Task | Est. Time | Priority |
|------|------|-----------|----------|
| 4.1.1 | Create `subscriptions` app with models | 2 hours | HIGH |
| 4.1.2 | Implement Stripe checkout endpoints | 3 hours | HIGH |
| 4.1.3 | Implement webhook handler | 2 hours | HIGH |
| 4.1.4 | Frontend subscription pages | 3 hours | HIGH |
| 4.2.1 | Create automation models | 2 hours | MEDIUM |
| 4.2.2 | OAuth connection endpoints (stub) | 2 hours | MEDIUM |
| 4.2.3 | Frontend automation page | 2 hours | MEDIUM |

---

## Model Context Protocol (MCP) Integration

### Overview

The automation service supports **dual-mode operation**:
1. **REST API Mode**: Traditional Django REST Framework endpoints at `/api/v1/automation/`
2. **MCP Mode**: Model Context Protocol server for AI agent integration

### MCP Server Architecture

The MCP server exposes automation capabilities as tools that AI models (Claude, GPT, etc.) can invoke:

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP SERVER                                  │
├─────────────────────────────────────────────────────────────────┤
│  Transport Layer (stdio or SSE)                                │
├─────────────────────────────────────────────────────────────────┤
│  Available Tools:                                               │
│  - list_social_profiles      - get_social_profile_status        │
│  - disconnect_social_profile - list_scheduled_content           │
│  - create_scheduled_content  - update_scheduled_content         │
│  - cancel_scheduled_content  - publish_content_now              │
│  - post_to_linkedin          - post_to_twitter                  │
│  - post_to_facebook          - list_automation_tasks            │
│  - get_platform_oauth_url                                       │
└─────────────────────────────────────────────────────────────────┘
```

### Starting the MCP Server

**Stdio Transport** (for Claude Desktop, VS Code):
```bash
cd ai-brand-automator
source ../.venv/bin/activate
python run_mcp_server.py --transport stdio
```

**SSE Transport** (for web clients):
```bash
cd ai-brand-automator
source ../.venv/bin/activate
python run_mcp_server.py --transport sse --host 0.0.0.0 --port 8001
```

**Debug Mode**:
```bash
python run_mcp_server.py --transport stdio --debug
```

### Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):
```json
{
  "mcpServers": {
    "automation": {
      "command": "python",
      "args": ["run_mcp_server.py"],
      "cwd": "/path/to/ai-brand-automator",
      "env": {
        "DJANGO_SETTINGS_MODULE": "brand_automator.settings"
      }
    }
  }
}
```

### VS Code Integration

Use the [mcp.json](ai-brand-automator/mcp.json) configuration file for VS Code Copilot integration.

### Key Files

| File | Purpose |
|------|---------|
| [automation/mcp_server.py](ai-brand-automator/automation/mcp_server.py) | MCP server with 13 tools |
| [run_mcp_server.py](ai-brand-automator/run_mcp_server.py) | Standalone runner script |
| [mcp.json](ai-brand-automator/mcp.json) | VS Code MCP configuration |

### MCP Tool Reference

| Tool | Description | Required Args |
|------|-------------|---------------|
| `list_social_profiles` | List all connected social accounts | `company_id` |
| `get_social_profile_status` | Check connection status | `profile_id` |
| `disconnect_social_profile` | Remove social connection | `profile_id` |
| `list_scheduled_content` | Get scheduled posts | `company_id` |
| `create_scheduled_content` | Schedule new post | `company_id`, `platform`, `content`, `scheduled_time` |
| `update_scheduled_content` | Modify scheduled post | `content_id`, (optional fields) |
| `cancel_scheduled_content` | Cancel scheduled post | `content_id` |
| `publish_content_now` | Publish immediately | `content_id` |
| `post_to_linkedin` | Direct LinkedIn post | `profile_id`, `content` |
| `post_to_twitter` | Direct Twitter post | `profile_id`, `content` |
| `post_to_facebook` | Direct Facebook post | `profile_id`, `content` |
| `list_automation_tasks` | Get automation jobs | `company_id` |
| `get_platform_oauth_url` | Get OAuth connect URL | `platform`, `company_id`, `redirect_uri` |

### Environment Variables for MCP

Add to `.env`:
```bash
# Social Platform OAuth (required for actual posting)
LINKEDIN_CLIENT_ID=<linkedin-client-id>
LINKEDIN_CLIENT_SECRET=<linkedin-client-secret>
TWITTER_CLIENT_ID=<twitter-client-id>
TWITTER_CLIENT_SECRET=<twitter-client-secret>
FACEBOOK_APP_ID=<facebook-app-id>
FACEBOOK_APP_SECRET=<facebook-app-secret>
```

### Testing the MCP Server

Multiple testing approaches are available:

#### 1. Python Test Script (Recommended)
```bash
cd ai-brand-automator
source ../.venv/bin/activate

python test_mcp_server.py           # Run all tests
python test_mcp_server.py --verbose # Verbose output
python test_mcp_server.py --live user@example.com  # Test with real user data
```

The test script verifies:
- Server metadata (name, version, description)
- Server creation
- All 13 tools are registered and callable
- Tool input validation
- Resources and prompts are registered
- Error handling for invalid inputs

#### 2. MCP Inspector (Interactive Web UI)
```bash
# Install MCP Inspector
pip install mcp-inspector

# Run inspector with your server
npx @anthropic-ai/mcp-inspector python run_mcp_server.py
```
Opens a web UI where you can browse tools, call them with custom arguments, and view responses.

#### 3. Claude Desktop Integration (Real-World Test)
Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):
```json
{
  "mcpServers": {
    "automation": {
      "command": "python",
      "args": ["run_mcp_server.py"],
      "cwd": "/path/to/ai-brand-automator",
      "env": {
        "DJANGO_SETTINGS_MODULE": "brand_automator.settings"
      }
    }
  }
}
```
Restart Claude Desktop, then ask Claude to use the automation tools.

#### 4. Direct JSON-RPC via stdin (Low-Level)
```bash
# List available tools
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python run_mcp_server.py

# List resources
echo '{"jsonrpc":"2.0","id":1,"method":"resources/list"}' | python run_mcp_server.py

# List prompts
echo '{"jsonrpc":"2.0","id":1,"method":"prompts/list"}' | python run_mcp_server.py
```

#### 5. SSE Transport Test (For Web Clients)
```bash
# Terminal 1: Start server with SSE
python run_mcp_server.py --transport sse --port 8001

# Terminal 2: Test with curl
curl -X POST http://localhost:8001/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

#### Test Files

| File | Purpose |
|------|---------|
| [test_mcp_server.py](ai-brand-automator/test_mcp_server.py) | Comprehensive test suite for MCP server |
| [run_mcp_server.py](ai-brand-automator/run_mcp_server.py) | Standalone runner for manual testing |

### Docker Deployment

The MCP server can be deployed via Docker using SSE transport for web clients and AI agents:

```bash
# Start MCP server alongside other services
docker-compose up mcp-server

# Or start all services including MCP
docker-compose up -d

# Check MCP server health
curl http://localhost:8001/health
```

**Docker Compose Service Configuration:**
```yaml
mcp-server:
  build:
    context: .
    dockerfile: Dockerfile
  command: python run_mcp_server.py --transport sse --host 0.0.0.0 --port 8001
  ports:
    - "8001:8001"
  environment:
    - DATABASE_URL=postgresql://postgres:postgres@db:5432/brand_automator
    - REDIS_URL=redis://redis:6379/0
    - DJANGO_SETTINGS_MODULE=brand_automator.settings
```

**Endpoints:**
| Endpoint | Description |
|----------|-------------|
| `http://localhost:8001/sse` | SSE connection endpoint for MCP clients |
| `http://localhost:8001/messages` | Message POST endpoint |
| `http://localhost:8001/health` | Health check for Docker/Kubernetes |

**Note:** For Claude Desktop or VS Code, use **stdio transport** (runs locally, not in Docker). Docker deployment is for **SSE transport** only (web clients, remote access).

---

## Key Technical Decisions

### Middleware Order (Critical)
```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # MUST BE FIRST for OPTIONS
    "django_tenants.middleware.main.TenantMainMiddleware",
    # ... other middleware
]
```

### Subscription Sync Pattern
After Stripe checkout, use `window.history.replaceState()` instead of `router.replace()` to avoid race conditions:
```tsx
// In subscription/page.tsx
if (success === 'true') {
  await subscriptionApi.syncSubscription();
  window.history.replaceState({}, '', '/subscription');  // Don't use router.replace()
}
// Then fetch fresh data
```

### AI Model Configuration
```python
# In ai_services/services.py
self.model_name = "gemini-2.0-flash"  # Updated from deprecated gemini-1.5-flash
```

---

## Phase 5: Railway Production Deployment

### 5.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RAILWAY PLATFORM                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│  │   NGINX     │   │   NEXT.JS   │   │   DJANGO    │   │   CELERY    │    │
│  │   PROXY     │──▶│  FRONTEND   │   │   BACKEND   │   │   WORKER    │    │
│  │  (Service)  │   │  (Service)  │   │  (Service)  │   │  (Service)  │    │
│  └─────────────┘   └─────────────┘   └──────┬──────┘   └──────┬──────┘    │
│                                              │                  │          │
│  ┌─────────────┐                      ┌──────▼──────────────────▼──────┐   │
│  │   CELERY    │                      │           REDIS               │   │
│  │    BEAT     │─────────────────────▶│         (Service)             │   │
│  │  (Service)  │                      │    Broker + Result Backend    │   │
│  └─────────────┘                      └───────────────────────────────┘   │
│                                                                             │
│                           ┌─────────────────┐                              │
│                           │   POSTGRES      │                              │
│                           │   (Neon DB)     │                              │
│                           │   External      │                              │
│                           └─────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Directory Structure

```
/deployment/
├── docker/
│   ├── backend/
│   │   └── Dockerfile           # Django API
│   ├── frontend/
│   │   └── Dockerfile           # Next.js
│   ├── celery-worker/
│   │   └── Dockerfile           # Celery Worker
│   ├── celery-beat/
│   │   └── Dockerfile           # Celery Beat Scheduler
│   └── nginx/
│       ├── Dockerfile           # Nginx Reverse Proxy
│       └── nginx.conf
│
├── railway/
│   └── railway.toml             # Railway configuration
│
├── scripts/
│   ├── start-backend.sh
│   ├── start-celery-worker.sh
│   ├── start-celery-beat.sh
│   └── health-check.sh
│
└── docker-compose.yml           # Local development orchestration
```

### 5.3 Implementation Phases

**Phase 5.1: Docker Configuration** (Est. 2-3 hours)
| Step | Task | Description |
|------|------|-------------|
| 5.1.1 | Backend Dockerfile | Multi-stage build for Django with Gunicorn |
| 5.1.2 | Frontend Dockerfile | Multi-stage build for Next.js standalone |
| 5.1.3 | Celery Worker Dockerfile | Based on backend with worker entrypoint |
| 5.1.4 | Celery Beat Dockerfile | Based on backend with beat entrypoint |
| 5.1.5 | Nginx Dockerfile | Reverse proxy configuration |
| 5.1.6 | Docker Compose | Local orchestration for testing |
| 5.1.7 | Startup Scripts | Entrypoint scripts for each service |

**Phase 5.2: Redis & Celery Configuration** (Est. 1-2 hours)
| Step | Task | Description |
|------|------|-------------|
| 5.2.1 | Celery Settings | Update Django settings for Celery |
| 5.2.2 | Redis Configuration | Configure Redis as broker/backend |
| 5.2.3 | Task Definitions | Define async tasks |
| 5.2.4 | Beat Schedule | Configure periodic tasks |

**Phase 5.3: Railway Configuration** (Est. 1-2 hours)
| Step | Task | Description |
|------|------|-------------|
| 5.3.1 | railway.toml | Railway service configuration |
| 5.3.2 | Environment Variables | Production secrets template |
| 5.3.3 | Health Checks | Configure Railway health monitoring |
| 5.3.4 | Domain Setup | Custom domain configuration |

**Phase 5.4: GitHub CI/CD Pipeline** (Est. 2-3 hours)
| Step | Task | Description |
|------|------|-------------|
| 5.4.1 | Update CI Workflow | Enhanced testing pipeline |
| 5.4.2 | Railway Deploy Action | Auto-deploy on merge to main |
| 5.4.3 | Environment Secrets | Configure GitHub secrets for Railway |
| 5.4.4 | Rollback Strategy | Manual rollback workflow |

### 5.4 Railway Services

| Service | Dockerfile | Port | Est. Cost |
|---------|------------|------|-----------|
| Backend (Django) | docker/backend/Dockerfile | 8000 | $5-20/mo |
| Frontend (Next.js) | docker/frontend/Dockerfile | 3000 | $5-15/mo |
| Celery Worker | docker/celery-worker/Dockerfile | - | $5-15/mo |
| Celery Beat | docker/celery-beat/Dockerfile | - | $5/mo |
| Redis | Railway Redis plugin | 6379 | $5-10/mo |
| **Total** | | | **~$25-65/mo** |

### 5.5 Environment Variables (Railway)

**Backend Service:**
```bash
SECRET_KEY=<django-secret>
DEBUG=False
ALLOWED_HOSTS=*.railway.app,<custom-domain>
DATABASE_URL=<neon-connection-string>
REDIS_URL=<railway-redis-url>
GOOGLE_API_KEY=<gemini-api-key>
STRIPE_SECRET_KEY=<stripe-secret>
STRIPE_WEBHOOK_SECRET=<webhook-secret>
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
```

**Frontend Service:**
```bash
NEXT_PUBLIC_API_URL=https://<backend-domain>
```

### 5.6 GitHub Actions Deployment

```yaml
# .github/workflows/deploy-railway.yml
name: Deploy to Railway
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: railwayapp/railway-github-link@v1
        with:
          token: ${{ secrets.RAILWAY_TOKEN }}
```

### 5.7 Required GitHub Secrets

Configure these secrets in your GitHub repository settings for CI/CD:

| Secret | Description | Required |
|--------|-------------|----------|
| `RAILWAY_TOKEN` | Railway API token for deployments | Yes |
| `RAILWAY_BACKEND_SERVICE` | Backend service ID in Railway | Yes |
| `RAILWAY_BACKEND_URL` | Backend URL for health checks | Yes |
| `RAILWAY_FRONTEND_SERVICE` | Frontend service ID in Railway | Yes |
| `RAILWAY_FRONTEND_URL` | Frontend URL for health checks | Yes |
| `RAILWAY_CELERY_WORKER_SERVICE` | Celery worker service ID | Optional |
| `RAILWAY_CELERY_BEAT_SERVICE` | Celery beat service ID | Optional |
| `RAILWAY_MCP_SERVER_SERVICE` | MCP server service ID | Optional |
| `RAILWAY_MCP_SERVER_URL` | MCP server URL (e.g., `https://mcp.yourdomain.com`) | Optional |

**MCP Server Environment Variables (Railway):**
```bash
# Required
DJANGO_SETTINGS_MODULE=brand_automator.settings
SECRET_KEY=<django-secret>
DATABASE_URL=<neon-connection-string>

# MCP Transport Configuration
MCP_PORT=8001
MCP_HOST=0.0.0.0
MCP_TRANSPORT=sse

# Optional - Social Platform OAuth
LINKEDIN_CLIENT_ID=<linkedin-client-id>
LINKEDIN_CLIENT_SECRET=<linkedin-client-secret>
TWITTER_CLIENT_ID=<twitter-client-id>
TWITTER_CLIENT_SECRET=<twitter-client-secret>
FACEBOOK_APP_ID=<facebook-app-id>
FACEBOOK_APP_SECRET=<facebook-app-secret>
```

---

**When fixing issues**: Always reference [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](docs/CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md) for detailed implementation guidance and use defensive programming patterns for tenant access.
