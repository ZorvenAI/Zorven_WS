# AI Brand Automator

> **Version**: 5.0.0 (Full Workflow Pipeline — WF1 Discovery + WF2 Brand Strategy + WF3 Campaign Activation + WF3.5 Intelligence Loop)
> **Status**: ✅ Production Ready
> **Last Updated**: April 28, 2026

**Multi-tenant SaaS platform for AI-powered brand building**

A Django REST Framework backend with Next.js 15 frontend and 24 Python FastAPI agent microservices that helps businesses create and manage their brand strategy, run AI-powered analysis pipelines, and automate advertising campaigns — all powered by Google Gemini 2.0 Flash, Anthropic Claude, and sequential pipeline orchestration.

## Features

### Core Platform
- 🔐 **Multi-tenant Architecture** — Schema-based data isolation with django-tenants
- 🤖 **AI Brand Strategy Generation** — Powered by Google Gemini 2.0 Flash
- 📝 **5-Step Onboarding** — Guided company setup with asset uploads and PDF export
- 💬 **AI Chatbot** — Interactive brand guidance with file search and auto-titling
- 📊 **Dynamic Dashboard** — Real-time metrics, recent activity, and overview cards
- 🔄 **Auto Token Refresh** — Seamless 7-day JWT authentication
- 📁 **File Upload** — Multi-file drag-and-drop with GCS integration and deduplication
- 💳 **Stripe Integration** — Subscription plans with checkout and billing portal
- 📱 **Mobile Ready** — Responsive design with network testing support

### Social Media Integrations (All Complete ✅)
| Platform | OAuth | Posting | Scheduling | Media | Analytics |
|----------|-------|---------|------------|-------|-----------|
| 🔗 LinkedIn | ✅ | ✅ | ✅ | ✅ | ✅ |
| 🐦 Twitter/X | ✅ | ✅ | ✅ | ✅ | ✅ |
| 📘 Facebook | ✅ | ✅ | ✅ | ✅ | ✅ |
| 📸 Instagram | ✅ | ✅ | ✅ | ✅ | ✅ |
| 📍 Google Business Profile | ✅ | ✅ | ✅ | ✅ | ✅ |

### Automation Features
- 📅 **Content Calendar** — Schedule and manage social media posts across platforms
- ⚡ **Celery Automation** — 6 task queues for background processing
- 🖼️ **Media Attachments** — Images, videos, documents with platform-specific limits
- 💾 **Draft Save/Restore** — Auto-save drafts with media support in compose modals
- 📊 **Social Analytics** — Engagement metrics and insights for all platforms
- 🤖 **MCP Server** — 23 tools for AI agent integration (Claude, GPT)

### AI Pipeline Orchestration ✅
- 🔗 **Pipeline-as-Code** — Manifest-driven DAG system for multi-agent pipelines
- 🧠 **Dynamic Pipeline Composition** — Gemini function-calling auto-detects intent and composes pipelines from the node catalog (chat mode)
- 📊 **Real-time Progress** — ThoughtTrace UI with per-node status tracking via Redis + polling
- 🔍 **Web Discovery** — Tavily-powered research with URL scraping and content cleaning
- ✍️ **Content Authoring** — SEO/AEO/GEO-compliant blog generation from research data
- 📱 **Social Publishing** — Platform-specific content adaptation and automated posting
- 💬 **Chat Auto-Titling** — Gemini Flash-powered session title generation via Kafka
- 🤖 **AI Assistant** — Conversational pipeline launcher with manifest auto-detection
- ❌ **Job Cancellation** — Redis-based cancel flag checked before each node
- 📈 **Sequential Execution** — Topological order (Kahn's algorithm) with per-node progress callbacks

### Workflow 1: Discovery & Research ✅
| Service | Port | Purpose |
|---------|------|---------|
| Pipeline Orchestrator | 8010 | Sequential DAG execution, callback reporting |
| Discovery Agent | 8020 | Web research via Tavily, URL scraping, HTML cleaning |
| Market Research Agent | 8021 | Market sizing, TAM/SAM/SOM analysis, trends |
| Competitor Intel Agent | 8022 | Competitor profiling, SWOT, benchmarking |
| Audience Persona Agent | 8023 | Audience persona profiling (Claude Sonnet 4) |
| Trend Cultural Agent | 8024 | Trend monitoring, cultural insights, opportunity alerts |
| VoC Agent | 8025 | Voice of Customer analysis, sentiment, NPS (Claude Sonnet 4) |
| Intelligence Agent | 8030 | ISO 10668 brand valuation, BSI scoring |

### Workflow 2: Brand Strategy ✅
| Service | Port | Purpose |
|---------|------|---------|
| Brand Positioning Agent | 8031 | Differentiation, perceptual mapping (Claude Sonnet 4) |
| Brand Architecture Agent | 8032 | Hierarchy tree, naming, portfolio growth (Claude Sonnet 4) |
| Brand Personality Agent | 8033 | Aaker 5D, archetypes, values, voice matrix (Claude Sonnet 4) |
| Brand Naming Agent | 8034 | Name candidates, availability checking, tagline synthesis (Claude Sonnet 4) |
| Brand Story Agent | 8035 | Origin stories, mission/vision, pitches, channel narratives (Claude Sonnet 4) |

### Workflow 3: Campaign Activation ✅
| Service | Port | Purpose |
|---------|------|---------|
| Campaign Architecture Agent | 8041 | Meta Ads blueprint, funnel mapping, audience targeting (Claude Sonnet 4) |
| Creative Generation Agent | 8042 | AI ad images (Nano Banana 2), ad copy, Meta compliance (Claude Sonnet 4) |
| Ad Publishing Agent | 8043 | Meta Ads API publishing, human approval gate (Claude Sonnet 4) |
| Campaign Optimization Agent | 8044 | Continuous optimization, Meta Insights/Management API (Claude Sonnet 4 + Celery Beat) |

### Workflow 3.5: Intelligence Loop ✅
| Service | Port | Purpose |
|---------|------|---------|
| Intelligence Loop Agent | 8045 | Consumes optimization learnings, extracts campaign insights, feeds RAG |

### Supporting Services ✅
| Service | Port | Purpose |
|---------|------|---------|
| Chat Titling Worker | 8040 | Auto-titles chat sessions via Gemini Flash + Kafka |
| Content Agent | 8050 | SEO/AEO/GEO-compliant blog authoring |
| Social Agent | 8060 | Platform-specific post adaptation, publishing via MCP |
| RAG Uploader Agent | 8070 | Persists documents to Vertex AI RAG Store |
| Brand Equity Calculator | 8090 | Public brand equity calculator (Anthropic Claude) |
| Odoo MCP Server | 8095 | Odoo ERP MCP bridge with 101 tools |
| Odoo Worker Agent | 8100 | Multi-persona Odoo worker, PAOR loop |

### Workflow Analytics Dashboard ✅
- 📊 **KPI Scorecard** — Real-time metric cards extracted from completed pipeline jobs
- 📈 **Trend Charts** — Time-series visualization with daily/weekly/monthly rollups
- ⚖️ **Period Comparison** — Side-by-side metric comparison across time ranges
- 🎯 **Sentiment Distribution** — Gauge visualization for brand sentiment health
- 📋 **Analytics Coverage** — Badge showing extraction completeness across pipelines
- 🔍 **Brand Affinity Verification** — 3-tier validation (input match, content scan, RAG)
- 🏗️ **18 Pipeline Extractors** — Per-workflow metric extraction from result_data

### Optimization Dashboard ✅
- 📊 **Campaign Performance Charts** — Real-time Meta Ads campaign metrics
- 🎯 **Campaign Selector** — Multi-campaign monitoring and comparison
- 💡 **Recommendations Engine** — AI-generated optimization suggestions
- ⚙️ **Optimization Settings** — Configurable guardrails and thresholds
- 📋 **Recent Actions List** — Audit trail of optimization actions taken
- 🔄 **Manual Tick Trigger** — On-demand optimization cycle with skip-reason feedback

### Intelligence Loop Dashboard ✅
- 📊 **Intelligence Reports** — Campaign insight extraction and analysis
- 🔄 **WF2 Approval Queue** — Human review gate for brand strategy updates
- 📈 **Learning Feed** — Continuous optimization learnings from WF3

### Workspace Management ✅
- 🎨 **Visual Workflow Editor** — React Flow-based pipeline canvas
- 📸 **Workflow Snapshots** — Frozen execution state for replay
- 🔗 **Chat↔Workflow Links** — Bidirectional navigation between chat and workspace
- 🔒 **Collaborative Editing Locks** — Redis-based (2h TTL) to prevent conflicts
- 📡 **Real-time Progress** — WebSocket updates via `WorkspaceConsumer`

### Dynamic Skill Loading ✅

Runtime skill system that dynamically injects contextual instructions into agent LLM prompts based on user intent. Skills are `.md` files loaded at orchestrator startup — adding a new skill requires no code changes.

> **155 skills** across all agents (28 general + 12 brand-positioning + 12 brand-architecture + 12 brand-personality + 14 brand-naming + 14 brand-story + 12 campaign-architecture + 12 creative-generation + 12 ad-publishing + 27 Odoo-specific).

### Media Curation Service ✅
- 🎬 **Multi-format Processing** — Documents, images, video, and audio
- 🔍 **AI Enrichment** — Entity extraction, summarization, keyword generation via Gemini
- 🛡️ **PII Redaction** — Cloud DLP integration with tenant-specific configuration
- 📊 **Structured Output** — Normalized JSON for downstream RAG indexing
- 🔄 **Event-Driven** — Kafka-based pipeline with retry and dead letter queue
- 🏗️ **Hexagonal Architecture** — Clean separation with Ports & Adapters pattern

### RAG Index Service ✅
- 🔍 **Document Indexing** — Upsert curated JSON documents into Vertex AI Data Store
- 🗑️ **Document Deletion** — Remove documents from the index on delete events
- ⏱️ **Rate Limiting** — Sliding window algorithm enforcing 600 req/min quota
- 🔄 **Event-Driven** — Kafka consumer with CloudEvents format
- 🏗️ **Hexagonal Architecture** — Clean separation with Ports & Adapters pattern

### Odoo ERP Integration ✅
- 🔧 **101 MCP Tools** — Full Odoo CRUD via Model Context Protocol
- 👥 **Multi-Persona Worker** — PAOR loop (Plan, Act, Observe, Reflect)
- 🔐 **RBAC Engine** — 16 YAML role definitions for tool-level access control
- 🏢 **Tenant Provisioning** — Automated Odoo company setup via Kafka events

### Google Business Profile ✅
- 📍 GBP listing CRUD operations
- 📝 GBP post management
- ⭐ Review management with AI-assisted replies
- 📈 GBP insights and analytics
- 🔧 10 dedicated MCP tools

## Tech Stack

### Backend
- **Django 4.2** + Django REST Framework
- **24 FastAPI Microservices** for agent pipeline execution
- **Sequential Pipeline Orchestration** with topological node execution
- **Kong Gateway** (DB-less mode) for API gateway, JWT offloading, rate limiting
- **PostgreSQL** (Neon hosted) with multi-tenancy
- **Google Gemini 2.0 Flash** for AI content generation
- **Anthropic Claude** (Sonnet 4) for brand strategy and campaign agents
- **Stripe** for subscription management
- **Celery 5.6** + Redis for background task processing (6 queues)
- **Kafka** (optional) for event streaming and audit logging (40+ topics)
- **JWT Authentication** with token refresh
- **MCP Server** (Model Context Protocol) with 23 tools

### Frontend
- **Next.js 15** + React 19
- **TypeScript** (strict mode) for type safety
- **Tailwind CSS v4** with "Digital Twilight" dark theme
- **React Flow** for visual workflow editing
- **Recharts** for analytics and optimization dashboards
- **Automatic API client** with token management and multi-tenancy headers

### Deployment
- **Railway** for production hosting (with change detection deploys)
- **Docker** for containerization
- **GitHub Actions** for CI/CD (8 test jobs)
- **3,300+ tests** (pytest + Hypothesis + microservice suites)

## Project Structure

```
.
├── ai-brand-automator/              # Django backend
│   ├── ai_services/                 # AI integration & chat (Gemini 2.0 Flash)
│   ├── analytics/                   # Workflow analytics (extractors, rollups, scorecard)
│   ├── automation/                  # Social media automation & MCP server
│   ├── data_ingestion/              # Data ingestion pipeline (Hexagonal)
│   ├── files/                       # File upload service
│   ├── intelligence_loop/           # Intelligence reports & WF2 approval queue
│   ├── media_curation/              # Media processing pipeline (Hexagonal)
│   ├── onboarding/                  # Company onboarding with PDF export
│   ├── optimization/                # Campaign optimization dashboard API
│   ├── orchestration/               # Pipeline orchestration (dispatch, callbacks, results)
│   ├── rag_index/                   # RAG Index Service (Hexagonal)
│   ├── subscriptions/               # Stripe subscription management
│   ├── tenants/                     # Multi-tenancy models
│   ├── workspace/                   # Workflow editor (React Flow, snapshots, WebSocket)
│   └── brand_automator/             # Django settings & Celery config
│
├── pipeline-orchestrator-svc/       # Pipeline engine (FastAPI :8010)
├── discovery-agent-svc/             # Web research agent (FastAPI :8020)
├── market-research-agent-svc/       # Market sizing agent (FastAPI :8021)
├── competitor-intel-agent-svc/      # Competitor profiling agent (FastAPI :8022)
├── audience-persona-agent-svc/      # Audience persona agent (FastAPI :8023)
├── trend-cultural-agent-svc/        # Trend monitoring agent (FastAPI :8024)
├── voc-agent-svc/                   # Voice of Customer agent (FastAPI :8025)
├── intelligence-agent-svc/          # Brand valuation agent (FastAPI :8030)
├── brand-positioning-agent-svc/     # Brand positioning agent (FastAPI :8031)
├── brand-architecture-agent-svc/    # Brand architecture agent (FastAPI :8032)
├── brand-personality-agent-svc/     # Brand personality agent (FastAPI :8033)
├── brand-naming-agent-svc/          # Brand naming agent (FastAPI :8034)
├── brand-story-agent-svc/           # Brand story agent (FastAPI :8035)
├── chat-titling-worker/             # Chat title generator (FastAPI :8040)
├── campaign-architecture-agent-svc/ # Campaign architecture agent (FastAPI :8041)
├── creative-generation-agent-svc/   # Creative generation agent (FastAPI :8042)
├── ad-publishing-agent-svc/         # Ad publishing agent (FastAPI :8043)
├── campaign-optimization-agent-svc/ # Campaign optimization agent (FastAPI :8044)
├── intelligence-loop-agent-svc/     # Intelligence loop agent (FastAPI :8045)
├── content-agent-service/           # Blog authoring agent (FastAPI :8050)
├── social-agent-service/            # Social publishing agent (FastAPI :8060)
├── rag-uploader-agent-service/      # RAG document archival agent (FastAPI :8070)
├── brand-equity-calculator-svc/     # Public brand equity calc (FastAPI :8090)
├── odoo-mcp-server-svc/             # Odoo ERP MCP bridge (FastAPI :8095)
├── odoo-worker-agent-svc/           # Odoo worker agent (FastAPI :8100)
│
├── ai-brand-automator-frontend/     # Next.js frontend
│   └── src/
│       ├── app/                     # Next.js pages
│       │   ├── automation/          # Social media automation
│       │   ├── brand-equity/        # Public brand equity calculator
│       │   ├── dashboard/           # Main dashboard
│       │   │   ├── pipelines/       # Pipeline management
│       │   │   ├── analysis/        # Brand equity reports
│       │   │   └── ai-assistant/    # Conversational pipeline launcher
│       │   ├── intelligence/        # Intelligence loop dashboard
│       │   ├── optimization/        # Campaign optimization dashboard
│       │   └── ...                  # auth, billing, chat, files, onboarding
│       ├── components/
│       │   ├── analytics/           # KPI scorecard, trend charts, distribution gauges
│       │   ├── optimization/        # Campaign metrics, recommendations, settings
│       │   ├── intelligence/        # Intelligence reports, approval queue
│       │   ├── workspace/           # Workflow canvas, editor components
│       │   ├── pipelines/           # Pipeline visualization, ThoughtTrace
│       │   ├── brand/               # Brand equity components
│       │   └── ...                  # auth, chat, dashboard, layout, ui
│       ├── hooks/                   # useAuth, usePollingJob, useTenantRole
│       └── lib/                     # API client, analytics, workspace, orchestration
│
├── vendor/odoo/community/           # Git submodule — Odoo Community Edition 19.0
├── tests/integration/               # Cross-service integration tests (3 phases)
├── deployment/                      # Master Docker Compose + Kong config
├── scripts/                         # E2E test scripts, GitHub issue automation
└── docs/                            # Architecture documentation
```

## Architecture

### Request Flow

```
Browser → Next.js (:3000) → apiClient (JWT auto-refresh, X-Tenant-ID) → Kong Gateway (:8000)
  → JWT validation, CORS, rate limiting → Django Backend (:8001) → Serializer → Model → PostgreSQL
```

### Pipeline Flow

```
Django dispatches job → Pipeline Orchestrator (:8010) → sequential node execution (Kahn's algorithm)

  WF1: Discovery & Research
  ├── discovery-agent (:8020) → web research
  ├── market-research-agent (:8021) → market sizing
  ├── competitor-intel-agent (:8022) → SWOT analysis
  ├── audience-persona-agent (:8023) → persona profiling
  ├── trend-cultural-agent (:8024) → trend monitoring
  ├── voc-agent (:8025) → voice of customer
  └── intelligence-agent (:8030) → brand valuation

  WF2: Brand Strategy
  ├── brand-positioning-agent (:8031) → differentiation
  ├── brand-architecture-agent (:8032) → portfolio hierarchy
  ├── brand-personality-agent (:8033) → Aaker 5D / archetypes
  ├── brand-naming-agent (:8034) → naming & taglines
  └── brand-story-agent (:8035) → narratives & pitches

  WF3: Campaign Activation
  ├── campaign-architecture-agent (:8041) → Meta Ads blueprint
  ├── creative-generation-agent (:8042) → AI ad creative
  ├── ad-publishing-agent (:8043) → Meta Ads publishing + approval gate
  └── campaign-optimization-agent (:8044) → continuous optimization

  WF3.5: Intelligence Loop
  └── intelligence-loop-agent (:8045) → extracts learnings → feeds RAG

  Supporting Agents
  ├── content-agent (:8050) → blog authoring
  ├── social-agent (:8060) → social posting
  ├── rag-uploader (:8070) → RAG archival
  └── odoo-worker (:8100) → ERP operations

  → Callback → Django AnalysisJob (atomic update) → extract_metrics_task (analytics)
```

**Two pipeline modes:**
- **Chat (auto-detect)**: `PipelineComposer` uses Gemini function-calling to dynamically compose a pipeline from the node catalog
- **Pipeline UI (manifest-driven)**: Fixed DAG defined in `PipelineManifest` from `seed_manifests.py`

### Data Pipeline (Hexagonal Architecture)

```
Upload → data_ingestion → Kafka → media_curation → Kafka → rag_index (Vertex AI)
```

Pipeline apps use **Pydantic domain models (not Django ORM)**, ABC ports, and concrete adapters.

### Analytics Pipeline

```
Job completes → result_handler.py → extract_metrics_task (Celery)
  → Brand affinity verification (3 tiers) → Pipeline-specific extractor
  → MetricSnapshot rows → Rollup aggregation (daily/weekly/monthly)
  → Cache invalidation → Kafka event (optional)
```

18 pipeline-specific extractors read KPIs from `result_data.node_results.<node_id>`. Nightly reconciliation via Celery Beat at 02:00 UTC.

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Kong Gateway | 8000 | External API entry point |
| Django Backend | 8001 | Internal only (via Kong) |
| Frontend | 3000 | Next.js development server |
| Pipeline Orchestrator | 8010 | Sequential DAG execution engine |
| Discovery Agent | 8020 | Web research service |
| Market Research Agent | 8021 | Market sizing, TAM/SAM/SOM |
| Competitor Intel Agent | 8022 | Competitor profiling, SWOT |
| Audience Persona Agent | 8023 | Persona generation |
| Trend Cultural Agent | 8024 | Trend monitoring |
| VoC Agent | 8025 | Voice of Customer analysis |
| Intelligence Agent | 8030 | Brand valuation (ISO 10668) |
| Brand Positioning Agent | 8031 | Positioning strategy |
| Brand Architecture Agent | 8032 | Portfolio hierarchy |
| Brand Personality Agent | 8033 | Personality & values |
| Brand Naming Agent | 8034 | Naming & taglines |
| Brand Story Agent | 8035 | Narrative & pitches |
| Chat Titling Worker | 8040 | Chat auto-titling |
| Campaign Architecture Agent | 8041 | Meta Ads campaign blueprint |
| Creative Generation Agent | 8042 | AI ad creative |
| Ad Publishing Agent | 8043 | Meta Ads publishing |
| Campaign Optimization Agent | 8044 | Continuous optimization |
| Intelligence Loop Agent | 8045 | Optimization learnings extraction |
| Content Agent | 8050 | Blog authoring service |
| Social Agent | 8060 | Social content adaptation |
| RAG Uploader Agent | 8070 | RAG document archival |
| Kafka UI | 8080 | Kafka monitoring (optional) |
| MCP Server | 8085 | AI agent tools (SSE) |
| Brand Equity Calculator | 8090 | Public brand equity (Anthropic Claude) |
| Odoo MCP Server | 8095 | Odoo ERP bridge (101 tools) |
| Odoo Worker Agent | 8100 | Multi-persona Odoo worker |
| Prompt Optimization Service | 8110 | MLflow prompt registry + GEPA optimization |
| MLflow Tracking Server | 5000 | Prompt registry & experiment tracking |
| MLflow Database | 5435 | MLflow PostgreSQL (host port) |

## Kong Gateway Architecture

Kong Gateway runs in **DB-less (declarative) mode** as the API entry point, providing JWT authentication offloading, rate limiting, and CORS handling.

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
                                                                  Anthropic Claude
                                                                  Stripe / Celery+Redis
```

- **JWT Offloading**: Kong validates JWT tokens at the edge; Django trusts pre-validated claims
- **Rate Limiting**: Configurable per-route limits (100 req/min API, 20 req/min auth)
- **CORS Handling**: Centralized CORS configuration for all origins
- **Request Transformation**: Header injection for tenant context
- **Health Checks**: Automatic backend health monitoring

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL database (or use Neon)
- Google Cloud account (for Gemini API)
- Redis (for Celery, caching, job tracking)

### Backend Setup

1. **Create virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
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
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   DB_NAME=your-database-name
   DB_USER=your-db-user
   DB_PASSWORD=your-db-password
   DB_HOST=your-host.neon.tech
   DB_PORT=5432
   GOOGLE_API_KEY=your-google-gemini-api-key
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   ```

4. **Run migrations**:
   ```bash
   python manage.py migrate_schemas --shared --noinput
   ```

5. **Seed data**:
   ```bash
   python manage.py seed_manifests               # Pipeline manifests
   python manage.py seed_metrics                  # Analytics MetricDefinitions
   python manage.py seed_subscription_plans       # Stripe plans
   ```

6. **Start development server**:
   ```bash
   python manage.py runserver 0.0.0.0:8001
   ```

7. **Start Celery** (background tasks):
   ```bash
   # Worker (default + orchestration queues)
   celery -A brand_automator worker -l info

   # Scheduler (publishing, stale jobs, rollup reconciliation)
   celery -A brand_automator beat -l info
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
   ```
   ```bash
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_BRAND_EQUITY_API_URL=http://localhost:8090
   ```

3. **Start development server**:
   ```bash
   npm run dev
   # Server runs at http://localhost:3000
   ```

### Docker Quick Start (Full Stack)

```bash
cd deployment

# Start all core services (Kong, Django, Frontend, 24 Microservices, Redis, Celery)
docker compose up --build

# Include Kafka for event streaming
docker compose --profile with-kafka up --build

# Include local PostgreSQL (instead of Neon)
docker compose --profile with-kafka --profile with-db up --build

# Tear down
docker compose down -v
```

### Microservices (all FastAPI + Python 3.12)

Each microservice follows the same pattern:
```bash
cd <service-dir>
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port <PORT> --reload
pytest tests/ -v
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/register/` — User registration with tenant creation
- `POST /api/v1/auth/login/` — Email-based JWT login
- `POST /api/v1/auth/token/refresh/` — Refresh access token

### Tenants (Workspaces)
- `GET /api/v1/tenants/me/` — List user's workspaces with roles
- `POST /api/v1/tenants/` — Create new workspace
- `POST /api/v1/tenants/{id}/switch/` — Switch active workspace (issues new JWT)
- `POST /api/v1/tenants/{id}/invite/` — Invite member to workspace
- `GET /api/v1/tenants/{id}/members/` — List workspace members

### Onboarding
- `GET|POST /api/v1/companies/` — Company CRUD
- `PATCH /api/v1/companies/{id}/` — Update company data (PATCH, not PUT)
- `POST /api/v1/companies/{id}/generate_brand_strategy/` — AI brand strategy
- `POST /api/v1/companies/{id}/generate_brand_identity/` — AI brand identity
- `GET|POST /api/v1/assets/` — Brand assets
- `POST /api/v1/assets/upload/` — File upload (HTTP 409 on duplicate)

### AI Services
- `POST /api/v1/ai/chat/` — AI chatbot interaction
- `GET /api/v1/ai/chat-sessions/` — Chat history
- `GET /api/v1/ai/generations/` — AI generation logs

### Pipeline Orchestration
- `POST /api/v1/orchestration/jobs/` — Create and dispatch a new analysis job
- `GET /api/v1/orchestration/jobs/` — List analysis jobs (tenant-filtered)
- `GET /api/v1/orchestration/jobs/{job_id}/` — Get job details with progress
- `GET /api/v1/orchestration/jobs/{job_id}/quick-status/` — Fast status (Redis-cached, for polling)
- `PATCH /api/v1/orchestration/jobs/{job_id}/callback/` — Orchestrator callback (service-to-service auth)
- `POST /api/v1/orchestration/jobs/{job_id}/cancel/` — Cancel running job
- `GET /api/v1/orchestration/manifests/` — List pipeline manifests
- `POST /api/v1/orchestration/manifests/` — Create pipeline manifest (admin only)

### Analytics
- `GET /api/v1/analytics/scorecard/` — KPI scorecard metrics
- `GET /api/v1/analytics/trends/` — Time-series trend data
- `GET /api/v1/analytics/comparison/` — Period comparison metrics
- `GET /api/v1/analytics/distribution/` — Sentiment distribution data
- `GET /api/v1/analytics/coverage/` — Analytics extraction coverage

### Optimization
- `GET /api/v1/optimization/campaigns/` — Campaign performance metrics
- `GET /api/v1/optimization/recommendations/` — AI optimization recommendations
- `POST /api/v1/optimization/trigger-tick/` — Manual optimization cycle trigger
- `GET /api/v1/optimization/settings/` — Optimization configuration

### Intelligence Loop
- `GET /api/v1/intelligence-loop/intelligence-reports/` — Intelligence reports
- `GET /api/v1/intelligence-loop/approval-queue/` — WF2 approval queue

### Workspace
- `GET|POST /api/v1/workspace/workflows/` — User workflows CRUD
- `GET /api/v1/workspace/workflows/{id}/snapshots/` — Workflow execution snapshots
- `POST /api/v1/workspace/workflows/{id}/lock/` — Acquire collaborative editing lock
- `WebSocket ws://host/ws/workspace/<tenant_id>/` — Real-time progress updates

### Subscriptions
- `GET /api/v1/subscriptions/plans/` — List subscription plans
- `GET /api/v1/subscriptions/status/` — Current subscription status
- `POST /api/v1/subscriptions/create-checkout-session/` — Create Stripe checkout
- `POST /api/v1/subscriptions/webhook/` — Handle Stripe webhooks
- `POST /api/v1/subscriptions/create-portal-session/` — Customer billing portal

### Social Media Automation
- `GET /api/v1/automation/social-profiles/` — List connected profiles
- `GET /api/v1/automation/social-profiles/status/` — Platform connection status
- `GET /api/v1/automation/{platform}/connect/` — Initiate OAuth
- `GET /api/v1/automation/{platform}/callback/` — OAuth callback
- `POST /api/v1/automation/{platform}/disconnect/` — Disconnect account
- `POST /api/v1/automation/{platform}/post/` — Post immediately

### Content Calendar
- `GET /api/v1/automation/content-calendar/` — List scheduled posts
- `POST /api/v1/automation/content-calendar/` — Create scheduled post
- `PUT /api/v1/automation/content-calendar/{id}/` — Edit scheduled post
- `GET /api/v1/automation/content-calendar/upcoming/` — Get upcoming posts
- `POST /api/v1/automation/content-calendar/{id}/publish/` — Publish post now

### Media Curation
- `POST /api/v1/media-curation/curate/` — Submit curation request
- `POST /api/v1/media-curation/curate/batch/` — Batch curation
- `GET /api/v1/media-curation/status/{event_id}/` — Curation status
- `GET|POST /api/v1/media-curation/tenant-config/` — Tenant configurations

### Google Business Profile
- `GET|POST /api/v1/automation/gbp/listings/` — GBP listings
- `POST /api/v1/automation/gbp/listings/{id}/posts/` — Create GBP post
- `GET /api/v1/automation/gbp/listings/{id}/reviews/` — GBP reviews
- `POST /api/v1/automation/gbp/reviews/{id}/reply/` — Reply to review
- `GET /api/v1/automation/gbp/listings/{id}/insights/` — GBP insights

## Service-to-Service Authentication

| Header | Direction | Purpose |
|--------|-----------|---------|
| `X-Service-Token` | Django → Orchestrator | Dispatch and cancel |
| `X-Callback-Token` | Orchestrator → Django | Callback authentication |
| `X-Worker-Token` | Chat Titling Worker → Django | Title update |
| `X-Service-Token` | Content/Social Agent → Django | Blog/post creation |
| `X-Tenant-ID` | Frontend → Django, Orchestrator → Odoo MCP | Tenant routing |
| *(none)* | Browser → Brand Equity Calculator | Public/unauthenticated |

## Multi-Tenancy

The application uses **schema-based multi-tenancy** with django-tenants:

- Each user gets a unique tenant on registration
- Data is isolated via tenant FK filtering in the shared (public) schema
- **Workspace Switcher** in the frontend lets users create/switch between workspaces
- **Role-based access**: owner, admin, editor, viewer roles per workspace
- `TenantMembershipMiddleware` reads `X-Tenant-ID` header (injected by frontend)

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

## Development

### Running Tests

**Backend (2,075+ tests)**:
```bash
cd ai-brand-automator
source ../.venv/bin/activate
pytest -v                          # All backend tests
pytest -m unit                     # Unit tests only
pytest -m property                 # Property-based tests (Hypothesis)
pytest analytics/tests/ -v         # Analytics tests
pytest orchestration/tests/ -v     # Orchestration tests
pytest media_curation/ -v          # Media curation tests
pytest --cov=. --cov-report=html   # With coverage
```

**Microservices (1,200+ tests)**:
```bash
cd pipeline-orchestrator-svc && pytest tests/ -v
cd discovery-agent-svc && pytest tests/ -v
cd market-research-agent-svc && pytest tests/ -v
cd competitor-intel-agent-svc && pytest tests/ -v
cd audience-persona-agent-svc && pytest tests/ -v
cd trend-cultural-agent-svc && pytest tests/ -v
cd voc-agent-svc && pytest tests/ -v
cd intelligence-agent-svc && pytest tests/ -v
cd brand-positioning-agent-svc && pytest tests/ -v
cd brand-architecture-agent-svc && pytest tests/ -v
cd brand-personality-agent-svc && pytest tests/ -v
cd brand-naming-agent-svc && pytest tests/ -v
cd brand-story-agent-svc && pytest tests/ -v
cd campaign-architecture-agent-svc && pytest tests/ -v
cd creative-generation-agent-svc && pytest tests/ -v
cd ad-publishing-agent-svc && pytest tests/ -v
cd campaign-optimization-agent-svc && pytest tests/ -v
cd intelligence-loop-agent-svc && pytest tests/ -v
cd content-agent-service && pytest tests/ -v
cd social-agent-service && pytest tests/ -v
cd chat-titling-worker && pytest tests/ -v
cd brand-equity-calculator-svc && pytest tests/ -v
cd odoo-mcp-server-svc && pytest tests/ -v
cd odoo-worker-agent-svc && pytest tests/ -v
cd rag-uploader-agent-service && pytest tests/ -v
```

**Integration Tests**:
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
black .                        # Format code (88 char lines)
flake8 .                       # Lint code
python manage.py check         # Django system check
```

**Frontend**:
```bash
npm run lint                   # ESLint
npm run build                  # TypeScript compilation check
npx tsc --noEmit               # TypeScript check only
```

## Security Features

- ✅ No hardcoded credentials (all via `decouple.config()` with defaults)
- ✅ JWT tokens with 60-min access + 7-day refresh
- ✅ Automatic token refresh with queue management
- ✅ Schema-based tenant data isolation
- ✅ Role-based permissions (owner, admin, editor, viewer)
- ✅ Encrypted OAuth tokens (Fernet encryption derived from SECRET_KEY)
- ✅ SSRF prevention (external URLs validated against `ALLOWED_URL_PREFIXES`)
- ✅ Input validation (`sanitize_text_input`, `sanitize_ai_prompt`, `validate_file_upload`)
- ✅ Callback payload size limits (≤ 1 MB)
- ✅ Service-to-service token authentication
- ✅ DB SSL (`sslmode=require`, `channel_binding=require` for Neon)

## User Flow

1. **Registration** → Create account + tenant
2. **Onboarding** → 5-step wizard (Company → Brand Voice → Audience → Assets → Review + PDF)
3. **Dashboard** → View metrics, recent activity, overview cards
4. **Chat** → Interact with AI for brand guidance (auto-titled via Gemini Flash)
5. **AI Assistant** → Launch analysis pipelines with conversational interface
6. **Pipelines** → Monitor pipeline execution with real-time ThoughtTrace progress
7. **Analysis** → View ISO 10668 brand equity reports and valuations
8. **Analytics** → KPI scorecard, trend charts, period comparison, sentiment distribution
9. **Workspace** → Visual workflow editor with React Flow
10. **Optimization** → Campaign performance, AI recommendations, manual tick triggers
11. **Intelligence** → Intelligence reports, WF2 approval queue, learning feed
12. **Automation** → Connect social profiles, create and schedule posts
13. **Brand Equity** → Public brand equity calculator (no login required)

## Media Specifications by Platform

| Platform | Image | Video | Document |
|----------|-------|-------|----------|
| LinkedIn | 8MB (JPEG, PNG, GIF) | 500MB (MP4) | 100MB (PDF, DOC, PPT) |
| Twitter/X | 5MB (JPEG, PNG, GIF) | 512MB (MP4) | N/A |
| Facebook | 4MB (JPEG, PNG) | 4GB (MP4) | N/A |
| Instagram | 8MB (JPEG, PNG) | 100MB (MP4) | N/A |
| GBP | 5MB (JPEG, PNG) | N/A | N/A |

## Media Curation Supported Formats

| Content Type | Formats | Features |
|-------------|---------|----------|
| Documents | PDF, DOC, TXT, HTML, MD, CSV | Text extraction, AI summarization |
| Images | PNG, JPEG, GIF, WebP, TIFF | OCR, Vision API, entity extraction |
| Video | MP4, WebM, MPEG, QuickTime | Speech-to-text, scene analysis |
| Audio | MP3, WAV, OGG, FLAC | Speech-to-text, transcription |

## Troubleshooting

### Backend Issues

**Database connection fails**:
- Check `.env` has correct DB credentials
- Ensure Neon database is running
- Verify `sslmode=require` for Neon

**AI generation returns fallback text**:
- Check `GOOGLE_API_KEY` is set in `.env`
- Verify API key is valid in Google AI Studio
- Ensure using `gemini-2.0-flash` model

**Token authentication fails**:
- Clear localStorage in browser
- Verify `SECRET_KEY` hasn't changed
- Check token hasn't expired (60 min access)

### Frontend Issues

**CORS errors**:
- Verify backend `CORS_ALLOWED_ORIGINS` includes `http://localhost:3000`
- **Critical**: `CorsMiddleware` must be FIRST in MIDDLEWARE list (before TenantMainMiddleware)

**401 Unauthorized**:
- Token expired — will auto-refresh
- If refresh fails, redirects to login
- Check `access_token` and `refresh_token` in localStorage

**Build fails**:
- Run `npm run build` to see TypeScript errors
- Check all imports are correct

## Contributing

1. Create feature branch from `main`
2. Make changes with conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`)
3. Test locally (backend + frontend)
4. Push and create pull request

## Documentation

- [Architecture Overview](ARCHITECTURE.md)
- [Agent Boundaries](AGENTS.md)
- [Copilot Instructions](.github/copilot-instructions.md)
- [Pipeline Orchestrator](pipeline-orchestrator-svc/CLAUDE.md)
- [Discovery Agent](discovery-agent-svc/CLAUDE.md)
- [Intelligence Agent](intelligence-agent-svc/CLAUDE.md)
- [Content Agent](content-agent-service/CLAUDE.md)
- [Social Agent](social-agent-service/CLAUDE.md)
- [Chat Titling Worker](chat-titling-worker/CLAUDE.md)
- [Brand Equity Calculator](brand-equity-calculator-svc/CLAUDE.md)
- [Odoo MCP Server](odoo-mcp-server-svc/CLAUDE.md)
- [Odoo Worker Agent](odoo-worker-agent-svc/CLAUDE.md)
- [Market Research Agent](market-research-agent-svc/CLAUDE.md)
- [Competitor Intel Agent](competitor-intel-agent-svc/CLAUDE.md)
- [Audience Persona Agent](audience-persona-agent-svc/CLAUDE.md)
- [Trend Cultural Agent](trend-cultural-agent-svc/CLAUDE.md)
- [VoC Agent](voc-agent-svc/CLAUDE.md)
- [Brand Positioning Agent](brand-positioning-agent-svc/CLAUDE.md)
- [Brand Architecture Agent](brand-architecture-agent-svc/CLAUDE.md)
- [Brand Personality Agent](brand-personality-agent-svc/CLAUDE.md)
- [Brand Naming Agent](brand-naming-agent-svc/CLAUDE.md)
- [Brand Story Agent](brand-story-agent-svc/CLAUDE.md)
- [Campaign Architecture Agent](campaign-architecture-agent-svc/CLAUDE.md)
- [Creative Generation Agent](creative-generation-agent-svc/CLAUDE.md)
- [Ad Publishing Agent](ad-publishing-agent-svc/CLAUDE.md)
- [Campaign Optimization Agent](campaign-optimization-agent-svc/CLAUDE.md)
- [Intelligence Loop Agent](intelligence-loop-agent-svc/CLAUDE.md)
- [Media Curation Service](ai-brand-automator/media_curation/README.md)
- [Deployment Guide](deployment/README.md)
- [Design System](ai-brand-automator-frontend/DESIGN_SYSTEM.md)

## License

See [LICENSE.md](docs/LICENSE.md)

## Status

**Current Version**: 5.0.0 (Full Workflow Pipeline — WF1 + WF2 + WF3 + WF3.5)
**Status**: ✅ Production Ready
**Deployment**: Railway (with change detection)
**Last Updated**: April 28, 2026

### Test Coverage
| Component | Tests | Status |
|-----------|-------|--------|
| **Django Backend** | **~2,075** | ✅ |
| Media Curation | 469 | ✅ |
| RAG Index | 348 | ✅ |
| Onboarding | 258 | ✅ |
| Automation | 252 | ✅ |
| Data Ingestion | 226 | ✅ |
| Tenants | 172 | ✅ |
| AI Services | 143 | ✅ |
| Orchestration | 123 | ✅ |
| Analytics | 50+ | ✅ |
| Workspace | 30+ | ✅ |
| Optimization | 30+ | ✅ |
| Other | 80+ | ✅ |
| **Microservices** | **~1,200** | ✅ |
| Pipeline Orchestrator | 171 | ✅ |
| Discovery Agent | 179 | ✅ |
| Market Research Agent | 100+ | ✅ |
| Competitor Intel Agent | 90+ | ✅ |
| Audience Persona Agent | 100+ | ✅ |
| Trend Cultural Agent | 50+ | ✅ |
| VoC Agent | 100+ | ✅ |
| Intelligence Agent | 100 | ✅ |
| Brand Positioning Agent | 40+ | ✅ |
| Brand Architecture Agent | 35+ | ✅ |
| Brand Personality Agent | 35+ | ✅ |
| Brand Naming Agent | 50+ | ✅ |
| Brand Story Agent | 35+ | ✅ |
| Campaign Architecture Agent | 45+ | ✅ |
| Creative Generation Agent | 25+ | ✅ |
| Ad Publishing Agent | 40+ | ✅ |
| Campaign Optimization Agent | 45+ | ✅ |
| Intelligence Loop Agent | 20+ | ✅ |
| Content Agent | 55 | ✅ |
| Social Agent | 89 | ✅ |
| Chat Titling Worker | 34 | ✅ |
| Brand Equity Calculator | 15+ | ✅ |
| Odoo MCP Server | 150+ | ✅ |
| Odoo Worker Agent | 60+ | ✅ |
| RAG Uploader Agent | 50+ | ✅ |
| **Integration Tests** | **60** | ✅ |
| **Total** | **~3,300+** | ✅ |
