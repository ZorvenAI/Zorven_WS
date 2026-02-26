# AI Brand Automator

> **Version**: 3.0.0 (AI Pipeline Orchestration + Agent Microservices)
> **Status**: ✅ Production Ready
> **Last Updated**: February 26, 2026

**Multi-tenant SaaS platform for AI-powered brand building**

A Django REST Framework backend with Next.js frontend and 6 FastAPI agent microservices that helps businesses create and manage their brand strategy, run AI-powered analysis pipelines, and automate social media — all powered by Google Gemini AI and LangGraph orchestration.

## Features

### Core Platform
- 🔐 **Multi-tenant Architecture** - Schema-based data isolation with django-tenants
- 🤖 **AI Brand Strategy Generation** - Powered by Google Gemini 2.0 Flash
- 📝 **5-Step Onboarding** - Guided company setup with asset uploads
- 💬 **AI Chatbot** - Interactive brand guidance and file search
- 📊 **Dynamic Dashboard** - Real-time metrics and activity tracking
- 🔄 **Auto Token Refresh** - Seamless 7-day authentication
- 📁 **File Upload** - Multi-file drag-and-drop with GCS integration
- 💳 **Stripe Integration** - Subscription plans with checkout and billing portal
- 📱 **Mobile Ready** - Responsive design with network testing support

### Social Media Integrations (All Complete ✅)
| Platform | OAuth | Posting | Scheduling | Media | Analytics |
|----------|-------|---------|------------|-------|-----------|
| 🔗 LinkedIn | ✅ | ✅ | ✅ | ✅ | ✅ |
| 🐦 Twitter/X | ✅ | ✅ | ✅ | ✅ | ✅ |
| 📘 Facebook | ✅ | ✅ | ✅ | ✅ | ✅ |
| 📸 Instagram | ✅ | ✅ | ✅ | ✅ | ✅ |
| 📍 Google Business Profile | ✅ | ✅ | ✅ | ✅ | ✅ |

### Automation Features
- 📅 **Content Calendar** - Schedule and manage social media posts across platforms
- ⚡ **Celery Automation** - Background task processing for scheduled posts
- 🖼️ **Media Attachments** - Images, videos, documents with platform-specific limits
- 💾 **Draft Save/Restore** - Auto-save drafts with media support in compose modals
- 📊 **Social Analytics** - Engagement metrics and insights for all platforms
- 🤖 **MCP Server** - 23 tools for AI agent integration (Claude, GPT)

### Google Business Profile ✅
- 📍 GBP listing CRUD operations
- 📝 GBP post management
- ⭐ Review management with AI-assisted replies
- 📈 GBP insights and analytics
- 🔧 10 dedicated MCP tools

### AI Pipeline Orchestration (NEW ✅)
- 🔗 **Pipeline-as-Code** - LangGraph-compatible manifest system for multi-agent pipelines
- 📊 **Real-time Progress** - ThoughtTrace UI with per-agent status tracking
- 🏦 **ISO 10668 Brand Valuation** - Royalty Relief NPV and Brand Strength Index scoring
- 🔍 **Web Discovery** - Tavily-powered research with URL scraping and content cleaning
- ✍️ **Content Authoring** - SEO/AEO/GEO-compliant blog generation from research data
- 📱 **Social Publishing** - Platform-specific content adaptation and automated posting
- 💬 **Chat Auto-Titling** - Gemini Flash-powered session title generation via Kafka
- 🤖 **AI Assistant** - Conversational pipeline launcher with manifest auto-detection

### Agent Microservices (NEW ✅)
| Service | Port | Purpose |
|---------|------|---------|
| Pipeline Orchestrator | 8010 | LangGraph DAG execution, callback reporting |
| Discovery Agent | 8020 | Web research via Tavily, URL scraping, HTML cleaning |
| Intelligence Agent | 8030 | ISO 10668 valuation, BSI scoring, competitive gap analysis |
| Chat Titling Worker | 8040 | Auto-titles chat sessions via Gemini Flash + Kafka |
| Content Agent | 8050 | SEO/AEO/GEO-compliant blog authoring |
| Social Agent | 8060 | Platform-specific post adaptation, publishing via MCP |

### Media Curation Service ✅
- 🎬 **Multi-format Processing** - Documents, images, video, and audio
- 🔍 **AI Enrichment** - Entity extraction, summarization, keyword generation via Gemini
- 🛡️ **PII Redaction** - Cloud DLP integration with tenant-specific configuration
- 📊 **Structured Output** - Normalized JSON for downstream RAG indexing
- 🔄 **Event-Driven** - Kafka-based pipeline with retry and dead letter queue
- ⚡ **Celery Tasks** - Background processing with status tracking via Redis
- 🏗️ **Hexagonal Architecture** - Clean separation with Ports & Adapters pattern
- 📈 **443 tests** with 86% coverage

### RAG Index Service (NEW ✅)
- 🔍 **Document Indexing** - Upsert curated JSON documents into Vertex AI Data Store
- 🗑️ **Document Deletion** - Remove documents from the index on delete events
- ⏱️ **Rate Limiting** - Sliding window algorithm enforcing 600 req/min quota
- 📊 **Status Tracking** - Redis-based sync status with TTL
- 🔄 **Event-Driven** - Kafka consumer with CloudEvents format
- ⚡ **Celery Tasks** - Background processing with retry logic
- 🏗️ **Hexagonal Architecture** - Clean separation with Ports & Adapters pattern
- 📈 **322 tests** covering full pipeline

## Tech Stack

### Backend
- **Django 4.2.16** + Django REST Framework
- **6 FastAPI Microservices** for agent pipeline execution
- **LangGraph** for multi-agent pipeline orchestration
- **Kong Gateway** (DB-less mode) for API gateway, JWT offloading, rate limiting
- **PostgreSQL** (Neon hosted) with multi-tenancy
- **Google Gemini 2.0 Flash** for AI content generation
- **Stripe** for subscription management
- **Celery 5.6** + Redis for background task processing
- **Kafka** (optional) for event streaming and audit logging
- **JWT Authentication** with token refresh
- **MCP Server** (Model Context Protocol) with 23 tools

### Frontend
- **Next.js 15** + React 19
- **TypeScript** for type safety
- **Tailwind CSS** for styling
- **Automatic API client** with token management

### Deployment
- **Railway** for production hosting (with change detection deploys)
- **Docker** for containerization
- **GitHub Actions** for CI/CD (8 test jobs)
- **2770+ tests** (pytest + Hypothesis + microservice suites)

## Project Structure

```
.
├── ai-brand-automator/              # Django backend
│   ├── ai_services/                 # AI integration & chat (Gemini 2.0 Flash)
│   ├── automation/                  # Social media automation & MCP server
│   ├── orchestration/               # Pipeline orchestration (NEW)
│   │   ├── models.py                # PipelineManifest, AnalysisJob
│   │   ├── views.py                 # Job CRUD, callback, cancel
│   │   ├── services.py              # OrchestratorDispatcher
│   │   ├── result_handler.py        # Pipeline result processing
│   │   ├── kafka_consumers.py       # Result + Trace consumers
│   │   └── tasks.py                 # Celery dispatch task
│   ├── media_curation/              # Media processing pipeline (Hexagonal)
│   ├── rag_index/                   # RAG Index Service (Hexagonal)
│   ├── data_ingestion/              # Data ingestion pipeline (Hexagonal)
│   ├── files/                       # File upload service
│   ├── onboarding/                  # Company onboarding
│   ├── subscriptions/               # Stripe subscription management
│   ├── tenants/                     # Multi-tenancy models
│   └── brand_automator/             # Django settings & Celery config
│
├── pipeline-orchestrator-svc/       # LangGraph pipeline engine (FastAPI :8010)
├── discovery-agent-svc/             # Web research agent (FastAPI :8020)
├── intelligence-agent-svc/          # Brand valuation agent (FastAPI :8030)
├── chat-titling-worker/             # Chat title generator (FastAPI :8040)
├── content-agent-service/           # Blog authoring agent (FastAPI :8050)
├── social-agent-service/            # Social publishing agent (FastAPI :8060)
│
├── ai-brand-automator-frontend/     # Next.js frontend
│   └── src/
│       ├── app/                     # Next.js pages
│       │   ├── automation/          # Social media automation
│       │   ├── dashboard/           # Main dashboard
│       │   │   ├── pipelines/       # Pipeline management (NEW)
│       │   │   ├── analysis/        # Brand equity reports (NEW)
│       │   │   ├── ai-assistant/    # Conversational pipeline launcher (NEW)
│       │   │   └── team/            # Team management
│       │   └── subscription/        # Billing management
│       ├── components/              # React components
│       │   └── pipelines/           # Pipeline visualization (NEW)
│       ├── hooks/                   # Custom hooks (useAuth, usePollingJob)
│       └── lib/                     # API client & utilities
│
├── tests/integration/               # Cross-service integration tests (NEW)
│   ├── phase1_contracts/            # API contract tests
│   ├── phase2_domain/               # Domain logic tests
│   └── phase3_stress/               # Load/stress tests
│
├── deployment/                      # Master Docker Compose + Railway configs
│   ├── docker/                      # Dockerfiles for core services
│   ├── scripts/                     # Startup scripts
│   └── docker-compose.yml           # All services orchestration
│
├── .github/workflows/               # CI/CD pipelines
│   ├── ci-cd.yml                    # 8-job test pipeline
│   └── deploy-railway.yml           # Change-detection deployment
│
└── docs/                            # Architecture documentation
```

## Kong Gateway Architecture

Kong Gateway runs in **DB-less (declarative) mode** as the API entry point, providing JWT authentication offloading, rate limiting, and CORS handling.

### Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │          Kong Gateway (:8000)           │
                    │  ┌─────────────────────────────────┐    │
  Frontend (:3000) ─┼─►│  JWT Auth │ Rate Limit │ CORS   │────┼──► Django Backend (:8001)
                    │  └─────────────────────────────────┘    │           │
                    └─────────────────────────────────────────┘           ▼
                                                                   PostgreSQL (Neon)
                                                                         │
                                                                         ▼
                                                                  Gemini 2.0 Flash
                                                                  Stripe / Celery+Redis
```

### Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Kong Gateway | 8000 | External API entry point |
| Django Backend | 8001 | Internal only (via Kong) |
| Kong Admin API | 8002 | Configuration/debugging |
| Frontend | 3000 | Next.js development server |
| Pipeline Orchestrator | 8010 | LangGraph pipeline engine |
| Discovery Agent | 8020 | Web research service |
| Intelligence Agent | 8030 | Brand valuation service |
| Chat Titling Worker | 8040 | Chat auto-titling |
| Content Agent | 8050 | Blog authoring service |
| Social Agent | 8060 | Social content adaptation |
| Kafka UI | 8080 | Kafka monitoring (optional) |
| MCP Server | 8085 | AI agent tools (SSE) |

### Key Features

- **JWT Offloading**: Kong validates JWT tokens at the edge; Django trusts pre-validated claims
- **Rate Limiting**: Configurable per-route limits (100 req/min API, 20 req/min auth)
- **CORS Handling**: Centralized CORS configuration for all origins
- **Request Transformation**: Header injection for tenant context
- **Health Checks**: Automatic backend health monitoring

### Configuration Files

| File | Purpose |
|------|---------|
| `deployment/docker/kong/kong.yaml` | Declarative Kong configuration |
| `deployment/docker/kong/docker-entrypoint.sh` | Environment variable substitution |
| `ai-brand-automator/docker-compose.yml` | Local development with Kong |
| `ai-brand-automator/brand_automator/middleware.py` | `KongAuthenticationMiddleware` |

### Running with Kong (Local Development)

```bash
# Start all services (Kong, Django, Redis, PostgreSQL)
cd ai-brand-automator
docker-compose up -d

# Frontend points to Kong at localhost:8000
cd ../ai-brand-automator-frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

### Running without Kong (Direct Backend)

```bash
# Django runs on port 8000 directly
cd ai-brand-automator
python manage.py runserver

# Frontend points directly to Django
cd ../ai-brand-automator-frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

### Environment Variables

```bash
# Backend - Enable Kong mode
KONG_ENABLED=True              # Trust Kong JWT validation

# Kong - Backend connection (production)
BACKEND_URL=https://your-backend.railway.app
BACKEND_HOST=your-backend.railway.app
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL database (or use Neon)
- Google Cloud account (for Gemini API)

### Backend Setup

1. **Create virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   cd ai-brand-automator
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

   **Required variables**:
   ```bash
   # Django
   SECRET_KEY=your-secret-key-here  # Generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1

   # Database (PostgreSQL)
   DB_NAME=your-database-name
   DB_USER=your-db-user
   DB_PASSWORD=your-db-password
   DB_HOST=your-host.neon.tech
   DB_PORT=5432

   # AI Services
   GOOGLE_API_KEY=your-google-gemini-api-key

   # Google Cloud Storage (optional for MVP)
   GS_BUCKET_NAME=your-bucket-name
   GS_PROJECT_ID=your-project-id
   GS_CREDENTIALS_PATH=path/to/service-account.json

   # CORS
   CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
   ```

4. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

5. **Seed subscription plans**:
   ```bash
   python manage.py seed_subscription_plans
   ```

6. **Start development server**:
   ```bash
   python manage.py runserver
   # Server runs at http://localhost:8000
   
   # For mobile/network testing:
   python manage.py runserver 0.0.0.0:8000
   ```

### Docker Quick Start (Full Stack)

For full-stack development with Kong Gateway, all microservices, and optional Kafka:

```bash
# From the project root
cd deployment

# Start all core services (Kong, Django, Frontend, 6 Microservices, Redis, Celery)
docker compose up --build

# Include Kafka for event streaming (chat titling, pipeline triggers)
docker compose --profile with-kafka up --build

# Include local PostgreSQL (instead of Neon)
docker compose --profile with-db up --build

# All profiles combined
docker compose --profile with-kafka --profile with-db --profile with-nginx up --build

# Verify services are running
curl http://localhost:8000/health/    # Via Kong
curl http://localhost:8010/health     # Pipeline Orchestrator
curl http://localhost:8020/health     # Discovery Agent
curl http://localhost:8030/health     # Intelligence Agent
```

7. **Start Celery for background tasks** (optional, for scheduled posting):
   ```bash
   # Terminal 1 - Start Redis (macOS)
   brew services start redis
   
   # Terminal 2 - Celery Worker
   cd ai-brand-automator
   ../.venv/bin/python -m celery -A brand_automator worker -l info
   
   # Terminal 3 - Celery Beat (scheduler)
   cd ai-brand-automator
   ../.venv/bin/python -m celery -A brand_automator beat -l info
   ```

### Frontend Setup

1. **Install dependencies**:
   ```bash
   cd ai-brand-automator-frontend
   npm install
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env.local
   # Edit .env.local
   ```

   **Required variables**:
   ```bash
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

3. **Start development server**:
   ```bash
   npm run dev
   # Server runs at http://localhost:3000
   ```

4. **Build for production**:
   ```bash
   npm run build
   npm start
   ```

## API Endpoints

### Authentication
- `POST /api/v1/auth/register/` - User registration with tenant creation
- `POST /api/v1/auth/login/` - Email-based JWT login
- `POST /api/v1/auth/token/refresh/` - Refresh access token

### Tenants (Workspaces)
- `GET /api/v1/tenants/me/` - List user's workspaces with roles
- `POST /api/v1/tenants/` - Create new workspace
- `POST /api/v1/tenants/{id}/switch/` - Switch active workspace (issues new JWT)
- `POST /api/v1/tenants/{id}/invite/` - Invite member to workspace
- `GET /api/v1/tenants/{id}/members/` - List workspace members

### Onboarding
- `GET|POST /api/v1/companies/` - Company CRUD
- `PUT /api/v1/companies/{id}/` - Update company data
- `POST /api/v1/companies/{id}/generate_brand_strategy/` - AI brand strategy
- `POST /api/v1/companies/{id}/generate_brand_identity/` - AI brand identity
- `GET|POST /api/v1/assets/` - Brand assets
- `POST /api/v1/assets/upload/` - File upload

### AI Services
- `POST /api/v1/ai/chat/` - AI chatbot interaction
- `GET /api/v1/ai/chat-sessions/` - Chat history
- `GET /api/v1/ai/generations/` - AI generation logs

### Subscriptions
- `GET /api/v1/subscriptions/plans/` - List subscription plans
- `GET /api/v1/subscriptions/status/` - Current subscription status
- `POST /api/v1/subscriptions/create-checkout-session/` - Create Stripe checkout
- `POST /api/v1/subscriptions/sync/` - Sync subscription from Stripe
- `POST /api/v1/subscriptions/webhook/` - Handle Stripe webhooks
- `POST /api/v1/subscriptions/create-portal-session/` - Customer billing portal
- `POST /api/v1/subscriptions/cancel/` - Cancel subscription

### Social Media Automation
- `GET /api/v1/automation/social-profiles/` - List connected profiles
- `GET /api/v1/automation/social-profiles/status/` - Platform connection status

#### LinkedIn
- `GET /api/v1/automation/linkedin/connect/` - Initiate LinkedIn OAuth
- `GET /api/v1/automation/linkedin/callback/` - OAuth callback handler
- `POST /api/v1/automation/linkedin/disconnect/` - Disconnect LinkedIn account
- `POST /api/v1/automation/linkedin/post/` - Post to LinkedIn immediately
- `POST /api/v1/automation/linkedin/media/upload/` - Upload media

#### Twitter/X
- `GET /api/v1/automation/twitter/connect/` - Initiate Twitter OAuth
- `GET /api/v1/automation/twitter/callback/` - OAuth callback handler
- `POST /api/v1/automation/twitter/disconnect/` - Disconnect Twitter account
- `POST /api/v1/automation/twitter/post/` - Post to Twitter immediately

#### Facebook
- `GET /api/v1/automation/facebook/connect/` - Initiate Facebook OAuth
- `GET /api/v1/automation/facebook/callback/` - OAuth callback handler
- `POST /api/v1/automation/facebook/disconnect/` - Disconnect Facebook account
- `POST /api/v1/automation/facebook/post/` - Post to Facebook immediately

#### Instagram
- `GET /api/v1/automation/instagram/connect/` - Initiate Instagram OAuth
- `GET /api/v1/automation/instagram/callback/` - OAuth callback handler
- `POST /api/v1/automation/instagram/disconnect/` - Disconnect Instagram account
- `POST /api/v1/automation/instagram/post/` - Post to Instagram immediately

#### Google Business Profile
- `GET /api/v1/automation/gbp/listings/` - List GBP listings
- `POST /api/v1/automation/gbp/listings/` - Create GBP listing
- `GET /api/v1/automation/gbp/listings/{id}/` - Get GBP listing details
- `PUT /api/v1/automation/gbp/listings/{id}/` - Update GBP listing
- `DELETE /api/v1/automation/gbp/listings/{id}/` - Delete GBP listing
- `POST /api/v1/automation/gbp/listings/{id}/posts/` - Create GBP post
- `GET /api/v1/automation/gbp/listings/{id}/posts/` - List GBP posts
- `GET /api/v1/automation/gbp/listings/{id}/reviews/` - Get GBP reviews
- `POST /api/v1/automation/gbp/reviews/{id}/reply/` - Reply to review
- `GET /api/v1/automation/gbp/listings/{id}/insights/` - Get GBP insights

#### Content Calendar
- `GET /api/v1/automation/content-calendar/` - List scheduled posts
- `POST /api/v1/automation/content-calendar/` - Create scheduled post
- `PUT /api/v1/automation/content-calendar/{id}/` - Edit scheduled post
- `GET /api/v1/automation/content-calendar/upcoming/` - Get upcoming posts
- `POST /api/v1/automation/content-calendar/{id}/publish/` - Publish post now
- `POST /api/v1/automation/content-calendar/{id}/cancel/` - Cancel scheduled post

### Media Curation
- `POST /api/v1/media-curation/curate/` - Submit single curation request
- `POST /api/v1/media-curation/curate/batch/` - Submit batch curation request
- `GET /api/v1/media-curation/status/{event_id}/` - Get curation status
- `POST /api/v1/media-curation/curate/sync/` - Synchronous curation (blocking)
- `GET /api/v1/media-curation/health/` - Service health check
- `GET /api/v1/media-curation/tenant-config/` - List tenant configurations
- `POST /api/v1/media-curation/tenant-config/` - Create tenant configuration
- `GET /api/v1/media-curation/tenant-config/{tenant_id}/` - Get tenant config
- `PUT /api/v1/media-curation/tenant-config/{tenant_id}/` - Update tenant config
- `DELETE /api/v1/media-curation/tenant-config/{tenant_id}/` - Delete tenant config

### Pipeline Orchestration
- `POST /api/v1/orchestration/jobs/` - Create and dispatch a new analysis job
- `GET /api/v1/orchestration/jobs/` - List analysis jobs (tenant-filtered)
- `GET /api/v1/orchestration/jobs/{job_id}/` - Get job details with progress
- `GET /api/v1/orchestration/jobs/{job_id}/quick-status/` - Fast status (Redis-cached, for polling)
- `PATCH /api/v1/orchestration/jobs/{job_id}/callback/` - Orchestrator callback (service-to-service auth)
- `POST /api/v1/orchestration/jobs/{job_id}/cancel/` - Cancel running job
- `GET /api/v1/orchestration/manifests/` - List pipeline manifests
- `POST /api/v1/orchestration/manifests/` - Create pipeline manifest (admin only)
- `GET /api/v1/orchestration/manifests/{id}/` - Manifest details

## User Flow

1. **Registration** → Create account + tenant
2. **Onboarding Step 1** → Company information
3. **Onboarding Step 2** → Brand details
4. **Onboarding Step 3** → Target audience
5. **Onboarding Step 4** → Upload assets (optional)
6. **Onboarding Step 5** → Review & generate brand strategy with AI
7. **Dashboard** → View metrics and recent activity
8. **Chat** → Interact with AI for brand guidance (auto-titled via Gemini Flash)
9. **Automation** → Connect social profiles, create and schedule posts
10. **AI Assistant** → Launch analysis pipelines with conversational interface
11. **Pipelines** → Monitor pipeline execution with real-time progress
12. **Analysis** → View ISO 10668 brand equity reports and valuations

## Development

### Running Tests

**Backend (2090+ tests)**:
```bash
cd ai-brand-automator
source ../.venv/bin/activate
pytest -v                          # All backend tests
pytest -m unit                     # Unit tests only
pytest -m property                 # Property-based tests (Hypothesis)
pytest automation/tests/ -v        # Automation tests
pytest orchestration/tests/ -v     # Orchestration tests (123)
pytest media_curation/ -v          # Media curation tests (469)
pytest --cov=. --cov-report=html   # With coverage
```

**Microservices (628 tests)**:
```bash
cd pipeline-orchestrator-svc && pytest tests/ -v    # Orchestrator (171)
cd discovery-agent-svc && pytest tests/ -v          # Discovery (179)
cd intelligence-agent-svc && pytest tests/ -v       # Intelligence (100)
cd chat-titling-worker && pytest tests/ -v          # Chat Titling (34)
cd content-agent-service && pytest tests/ -v        # Content Agent (55)
cd social-agent-service && pytest tests/ -v         # Social Agent (89)
```

**Integration Tests (60 tests)**:
```bash
cd tests/integration
pytest phase1_contracts/ -v   # API contract tests
pytest phase2_domain/ -v      # Domain logic tests
pytest phase3_stress/ -v      # Stress tests
```

**Frontend**:
```bash
cd ai-brand-automator-frontend
npm test                       # Run tests
npm test -- --coverage         # With coverage (60% threshold)
```

### Code Quality

**Backend**:
```bash
black .                        # Format code
flake8 .                       # Lint code
python manage.py check         # Django system check
```

**Frontend**:
```bash
npm run lint                   # ESLint
npm run build                  # TypeScript compilation check
```

## Multi-Tenancy

The application uses **schema-based multi-tenancy** with django-tenants:

- Each user gets a unique tenant on registration
- Data is isolated via tenant FK filtering in the shared (public) schema
- `PUBLIC_SCHEMA_NAME = 'public'` for shared data
- `TENANT_MODEL = 'tenants.Tenant'`
- `TENANT_DOMAIN_MODEL = 'tenants.Domain'`
- **Workspace Switcher** in the frontend lets users create/switch between workspaces
- **Role-based access**: owner, admin, editor, viewer roles per workspace

### Tenant-Scoped Queries

All models have a nullable `tenant` FK. Queries use the backward-compatible Q() pattern:

```python
from django.db.models import Q

tenant = getattr(request, 'tenant', None)
if tenant:
    qs = Model.objects.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
else:
    qs = Model.objects.filter(tenant__isnull=True)
```

### Tenant Creation

Automatic on user registration:
```python
tenant = Tenant.objects.create(
    schema_name=f'tenant_{user.id}',
    name=f"{user.username}'s Company"
)
```

## Security Features

- ✅ No hardcoded credentials (all in .env)
- ✅ JWT tokens with 60-min access + 7-day refresh
- ✅ Automatic token refresh with queue management
- ✅ Authentication guards on all protected routes
- ✅ CORS properly configured with allowed headers
- ✅ Schema-based tenant data isolation
- ✅ IsAuthenticated permission on all API endpoints

## Environment Variables Reference

### Backend (.env)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `SECRET_KEY` | ✅ Yes | Django secret key | Generate with Django command |
| `DEBUG` | ✅ Yes | Debug mode | `True` or `False` |
| `DB_NAME` | ✅ Yes | PostgreSQL database | `ai_brand_automator` |
| `DB_USER` | ✅ Yes | Database user | `postgres` |
| `DB_PASSWORD` | ✅ Yes | Database password | `your-secure-password` |
| `DB_HOST` | ✅ Yes | Database host | `ep-xxx.neon.tech` |
| `GOOGLE_API_KEY` | ✅ Yes | Gemini API key | `AIza...` |
| `GS_BUCKET_NAME` | ⚠️ Optional | GCS bucket | `my-bucket` |
| `GS_PROJECT_ID` | ⚠️ Optional | GCP project | `my-project-123` |
| `CORS_ALLOWED_ORIGINS` | ⚠️ Optional | Frontend URLs | `http://localhost:3000` |
| `STRIPE_SECRET_KEY` | ✅ Yes | Stripe secret key | `sk_test_...` |
| `STRIPE_PUBLISHABLE_KEY` | ✅ Yes | Stripe public key | `pk_test_...` |
| `STRIPE_WEBHOOK_SECRET` | ⚠️ Optional | Webhook signing secret | `whsec_...` |
| `STRIPE_PRICE_BASIC` | ✅ Yes | Basic plan price ID | `price_...` |
| `STRIPE_PRICE_PRO` | ✅ Yes | Pro plan price ID | `price_...` |
| `STRIPE_PRICE_ENTERPRISE` | ✅ Yes | Enterprise price ID | `price_...` |
| `LINKEDIN_CLIENT_ID` | ⚠️ Optional | LinkedIn OAuth app ID | `77xxx...` |
| `LINKEDIN_CLIENT_SECRET` | ⚠️ Optional | LinkedIn OAuth secret | `WPLxxx...` |
| `LINKEDIN_REDIRECT_URI` | ⚠️ Optional | OAuth callback URL | `http://localhost:8000/api/v1/automation/linkedin/callback/` |
| `TWITTER_CLIENT_ID` | ⚠️ Optional | Twitter OAuth app ID | `xxx...` |
| `TWITTER_CLIENT_SECRET` | ⚠️ Optional | Twitter OAuth secret | `xxx...` |
| `FACEBOOK_APP_ID` | ⚠️ Optional | Facebook app ID | `xxx...` |
| `FACEBOOK_APP_SECRET` | ⚠️ Optional | Facebook app secret | `xxx...` |
| `INSTAGRAM_CLIENT_ID` | ⚠️ Optional | Instagram client ID | `xxx...` |
| `INSTAGRAM_CLIENT_SECRET` | ⚠️ Optional | Instagram client secret | `xxx...` |
| `GOOGLE_CLIENT_ID` | ⚠️ Optional | Google OAuth client ID | `xxx...` |
| `GOOGLE_CLIENT_SECRET` | ⚠️ Optional | Google OAuth client secret | `xxx...` |
| `CELERY_BROKER_URL` | ⚠️ Optional | Redis broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | ⚠️ Optional | Redis result backend | `redis://localhost:6379/0` |
| `KAFKA_BOOTSTRAP_SERVERS` | ⚠️ Optional | Kafka brokers | `localhost:9092` |
| `MEDIA_CURATION_REDIS_URL` | ⚠️ Optional | Redis for curation cache | `redis://localhost:6379/1` |
| `GCS_BUCKET_NAME` | ⚠️ Optional | GCS bucket for curated output | `media-curation-output` |
| `ORCHESTRATOR_URL` | ⚠️ Optional | Pipeline orchestrator URL | `http://localhost:8010` |
| `ORCHESTRATOR_SERVICE_TOKEN` | ⚠️ Optional | Service-to-service auth for dispatch | (secret) |
| `ORCHESTRATOR_CALLBACK_TOKEN` | ⚠️ Optional | Callback auth from orchestrator | (secret) |
| `ORCHESTRATOR_TIMEOUT` | ⚠️ Optional | HTTP timeout for dispatch (seconds) | `30` |
| `BACKEND_URL` | ⚠️ Optional | Backend URL for callbacks | `http://localhost:8001` |
| `ORCHESTRATION_KAFKA_ENABLED` | ⚠️ Optional | Use Kafka dispatch vs HTTP | `false` |
| `WORKER_TOKEN` | ⚠️ Optional | Auth for chat-titling-worker | (secret) |

### Frontend (.env.local)

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | ✅ Yes | Backend API URL | `http://localhost:8000` |

## Troubleshooting

### Backend Issues

**Database connection fails**:
- Check `.env` has correct DB credentials
- Ensure Neon database is running
- Verify `sslmode=require` for Neon

**AI generation returns fallback text**:
- Check `GOOGLE_API_KEY` is set in `.env`
- Verify API key is valid in Google AI Studio
- Check rate limits haven't been exceeded
- Ensure using `gemini-2.0-flash` model (1.5 is deprecated)

**Token authentication fails**:
- Clear localStorage in browser
- Verify `SECRET_KEY` hasn't changed
- Check token hasn't expired (60 min access)

### Frontend Issues

**CORS errors**:
- Verify backend `CORS_ALLOWED_ORIGINS` includes `http://localhost:3000`
- Check frontend uses correct API URL
- Ensure both servers are running
- **Critical**: `CorsMiddleware` must be FIRST in MIDDLEWARE list (before TenantMainMiddleware)

**Mobile/Network testing 404 errors**:
- Add your network IP to tenant domains in database:
  ```python
  from tenants.models import Tenant, Domain
  tenant = Tenant.objects.get(schema_name='public')
  Domain.objects.get_or_create(domain='<your-ip>', defaults={'tenant': tenant, 'is_primary': False})
  ```

**Build fails**:
- Run `npm run build` to see TypeScript errors
- Check all imports are correct
- Verify all required components exported

**401 Unauthorized**:
- Token expired - will auto-refresh
- If refresh fails, redirects to login
- Check `access_token` and `refresh_token` in localStorage

## Contributing

1. Create feature branch from `main`
2. Make changes with descriptive commits
3. Test locally (backend + frontend)
4. Push and create pull request

## Documentation

- [MVP Architecture](docs/ai_brand_automator_mvp_architecture.md) - Complete architecture overview
- [Architecture Plan](docs/ai_brand_automator_mvp_plan.md) - Original MVP plan
- [Codebase Analysis](docs/CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md) - Implementation details
- [Copilot Instructions](.github/copilot-instructions.md) - AI pair programming guide
- [LinkedIn Integration](ai-brand-automator/automation/docs/LINKEDIN_INTEGRATION_REPORT.md)
- [Twitter Integration](ai-brand-automator/automation/docs/TWITTER_INTEGRATION_REPORT.md)
- [Facebook Integration](ai-brand-automator/automation/docs/FACEBOOK_INTEGRATION_REPORT.md)
- [Instagram Integration](ai-brand-automator/automation/docs/INSTAGRAM_INTEGRATION_REPORT.md)
- [GBP Implementation](ai-brand-automator/automation/docs/GOOGLE_BUSINESS_PROFILE_IMPLEMENTATION_PLAN.md)
- [Media Curation Service](ai-brand-automator/media_curation/README.md)
- [Pipeline Orchestrator](pipeline-orchestrator-svc/CLAUDE.md)
- [Discovery Agent](discovery-agent-svc/CLAUDE.md)
- [Intelligence Agent](intelligence-agent-svc/CLAUDE.md)
- [Content Agent](content-agent-service/CLAUDE.md)
- [Social Agent](social-agent-service/CLAUDE.md)
- [Chat Titling Worker](chat-titling-worker/CLAUDE.md)
- [Deployment Guide](deployment/README.md)

## License

See [LICENSE.md](docs/LICENSE.md)

## Status

**Current Version**: 3.0.0 (AI Pipeline Orchestration + Agent Microservices)
**Status**: ✅ Production Ready
**Deployment**: Railway (with change detection)
**Last Updated**: February 26, 2026

### Test Coverage
| Component | Tests | Status |
|-----------|-------|--------|
| **Django Backend** | | |
| Media Curation | 469 | ✅ |
| RAG Index | 348 | ✅ |
| Onboarding | 258 | ✅ |
| Automation | 252 | ✅ |
| Data Ingestion | 226 | ✅ |
| Tenants | 172 | ✅ |
| AI Services | 143 | ✅ |
| Orchestration | 123 | ✅ |
| Files | 18 | ✅ |
| Other (conftest, etc.) | 80+ | ✅ |
| **Microservices** | | |
| Discovery Agent | 179 | ✅ |
| Pipeline Orchestrator | 171 | ✅ |
| Intelligence Agent | 100 | ✅ |
| Social Agent | 89 | ✅ |
| Content Agent | 55 | ✅ |
| Chat Titling Worker | 34 | ✅ |
| **Integration Tests** | 60 | ✅ |
| **Total** | **~2770** | ✅ |

### Completed Features
- ✅ Multi-tenant authentication
- ✅ User registration with tenant creation
- ✅ 5-step onboarding flow
- ✅ AI brand strategy generation (Gemini 2.0 Flash)
- ✅ AI brand identity with color palettes
- ✅ Dynamic dashboard
- ✅ Token refresh
- ✅ File upload UI
- ✅ Chat interface with auto-titling
- ✅ Stripe subscription management
- ✅ Checkout flow with plan sync
- ✅ Mobile/network testing support
- ✅ **LinkedIn** - OAuth, posting, scheduling, media, analytics
- ✅ **Twitter/X** - OAuth with PKCE, threads, media uploads, analytics
- ✅ **Facebook** - Page posting, stories, carousels, video uploads
- ✅ **Instagram** - OAuth, posting, stories, reels, carousels
- ✅ **Google Business Profile** - Listings, posts, reviews, insights
- ✅ Content Calendar with scheduling
- ✅ Celery-based automatic publishing (every 60 seconds)
- ✅ MCP Server with 23 tools for AI agents
- ✅ Railway production deployment
- ✅ CI/CD with GitHub Actions (8 test jobs)
- ✅ 2770+ automated tests
- ✅ **Media Curation Service** - AI-powered content processing pipeline
- ✅ **RAG Index Service** - Vertex AI document indexing pipeline
- ✅ **Multi-Tenancy** - Schema-based tenant isolation with django-tenants
- ✅ **Workspace Switcher** - Create/switch workspaces in the frontend
- ✅ **Tenant-Scoped Automation** - All social posting and calendar entries scoped by tenant
- ✅ **Pipeline Orchestration** - LangGraph-based multi-agent pipeline execution
- ✅ **6 Agent Microservices** - Orchestrator, Discovery, Intelligence, Content, Social, Chat Titling
- ✅ **ISO 10668 Brand Valuation** - Royalty Relief NPV and Brand Strength Index scoring
- ✅ **AI Assistant** - Conversational pipeline launcher with ThoughtTrace progress
- ✅ **Pipeline Dashboard** - Real-time pipeline monitoring and management
- ✅ **Analysis Dashboard** - Brand equity reports and valuation history
- ✅ **Chat Auto-Titling** - Gemini Flash-powered session titles via Kafka
- ✅ **Service-to-Service Auth** - X-Service-Token, X-Callback-Token patterns
- ✅ **Cross-Service Integration Tests** - 3-phase contract, domain, and stress tests

### Media Curation Supported Formats

| Content Type | Formats | Features |
|-------------|---------|----------|
| Documents | PDF, DOC, TXT, HTML, MD, CSV | Text extraction, AI summarization |
| Images | PNG, JPEG, GIF, WebP, TIFF | OCR, Vision API, entity extraction |
| Video | MP4, WebM, MPEG, QuickTime | Speech-to-text, scene analysis |
| Audio | MP3, WAV, OGG, FLAC | Speech-to-text, transcription |

### Media Specifications by Platform

| Platform | Image | Video | Document |
|----------|-------|-------|----------|
| LinkedIn | 8MB (JPEG, PNG, GIF) | 500MB (MP4) | 100MB (PDF, DOC, PPT) |
| Twitter/X | 5MB (JPEG, PNG, GIF) | 512MB (MP4) | N/A |
| Facebook | 4MB (JPEG, PNG) | 4GB (MP4) | N/A |
| Instagram | 8MB (JPEG, PNG) | 100MB (MP4) | N/A |
| GBP | 5MB (JPEG, PNG) | N/A | N/A |

### Future Enhancements (Post-MVP)
See [Architecture Document](docs/ai_brand_automator_mvp_architecture.md#future-enhancements-post-mvp) for Phases 9-17:
- Phase 9: Video & Content (YouTube, TikTok, Pinterest)
- Phase 10: E-commerce (Shopify, Amazon)
- ~~Phase 11: Analytics & Reporting~~ → Replaced by Media Curation Service
- Phase 12: Team & Collaboration
- Phase 13-17: Advanced AI, Marketing, Enterprise features
