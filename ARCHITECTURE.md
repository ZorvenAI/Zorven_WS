# ARCHITECTURE.md — AI Brand Automator

> The Map: High-level system architecture for long-horizon reasoning. Shows how data flows through the platform.

## System Overview

AI Brand Automator is a multi-tenant SaaS platform where users onboard companies, upload brand assets, and the AI generates brand strategies, manages social media, schedules content, and integrates Google Business Profiles.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              USER BROWSER                                    │
│                                                                              │
│   Next.js 15 (React 19 + TypeScript + Tailwind v4)  — Port 3000             │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│   │  Auth    │ │ Onboard  │ │Dashboard │ │ AI Chat  │ │ Social/Automation│  │
│   │  Pages   │ │ Wizard   │ │ + Files  │ │  Page    │ │  Pages           │  │
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
│  │  ├── auth/         → Register, Login, JWT Refresh, Password Reset   │   │
│  │  ├── (root)        → Companies, BrandAssets, Onboarding Progress    │   │
│  │  ├── ai/           → Chat, Content Generation (Gemini 2.0 Flash)    │   │
│  │  ├── subscriptions/→ Stripe Plans, Checkout, Webhooks               │   │
│  │  ├── automation/   → Social Profiles, Content Calendar, Posting     │   │
│  │  ├── ingestion/    → File Processing Pipeline API                   │   │
│  │  ├── curation/     → Media Curation Pipeline API                    │   │
│  │  └── rag-index/    → Document Sync to Vertex AI                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  onboarding  │  │  ai_services │  │  automation  │  │ subscriptions│   │
│  │  Company +   │  │  Gemini AI   │  │  Social +    │  │  Stripe      │   │
│  │  Assets      │  │  Singleton   │  │  GBP + MCP   │  │  Billing     │   │
│  └──────┬───────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│         │                                                                  │
│         ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              DATA PIPELINE (Hexagonal Architecture)                 │   │
│  │                                                                     │   │
│  │  Upload → data_ingestion ──Kafka──► media_curation ──Kafka──► rag_index │
│  │           (validate +       │       (OCR, PII,        │      (Vertex AI │
│  │            extract)         │        AI enrich)       │       vectors)  │
│  │                             │                         │                 │
│  │         domain/ ports/ adapters/ (Pydantic, not ORM)                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────┘
         │              │              │               │
         ▼              ▼              ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ PostgreSQL   │ │    Redis     │ │ Google Cloud  │ │   Kafka      │
│ (Neon)       │ │  (Celery +   │ │  Storage     │ │ (Event       │
│ Multi-tenant │ │   Caching)   │ │  2 Buckets   │ │  Streaming)  │
│ schemas      │ │              │ │ raw + curated │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

## Core Data Flows

### 1. User Registration & Onboarding

```
Browser → POST /api/v1/auth/register/
       → POST /api/v1/auth/login/ → JWT (access + refresh tokens)
       → POST /api/v1/companies/ (create company)
       → POST /api/v1/companies/{id}/assets/ (upload brand assets → GCS)
       → POST /api/v1/companies/{id}/generate-brand-strategy/ (Gemini AI)
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
│  IngestionRecord, CurationRecord                 │
│                                                  │
│  All models have nullable tenant FK:             │
│  tenant = ForeignKey(Tenant, null=True)           │
└─────────────────────────────────────────────────┘

All apps run in SHARED schema. Queries filter by tenant FK defensively.
```

## Process Architecture (Procfile)

| Process | Role | Command |
|---------|------|---------|
| `web` | HTTP API server | Gunicorn (4 workers, 2 threads) |
| `worker` | General Celery worker | Default queue |
| `beat` | Celery scheduler | Every 60s: publish_scheduled_posts |
| `ingestion-worker` | Ingestion Celery worker | `ingestion` queue |
| `ingestion-consumer` | Kafka → Ingestion | `run_ingestion` command |
| `curation-worker` | Curation Celery worker | `curation` queue |
| `curation-consumer` | Kafka → Curation | `run_curation_consumer` command |
| `rag-index-consumer` | Kafka → RAG sync | `consume_sync_events` command |

## External Service Integration

| Service | Purpose | Auth Method |
|---------|---------|------------|
| Google Gemini 2.0 Flash | AI content generation | API key (`GOOGLE_API_KEY`) |
| Google Cloud Storage | File storage (2 buckets) | Service account JSON |
| Stripe | Payments & subscriptions | Secret key + webhooks |
| LinkedIn API | OAuth + posting + analytics | OAuth 2.0 + page tokens |
| Twitter/X API | OAuth + posting + analytics | OAuth 2.0 |
| Facebook Graph API | OAuth + posting + analytics | OAuth 2.0 + page tokens |
| Instagram Graph API | OAuth + posting + analytics | Via Facebook page tokens |
| Google Business Profile | OAuth + posts + reviews | OAuth 2.0 |
| Apache Kafka | Event streaming (pipeline) | SASL/SSL or plaintext |
| Neon PostgreSQL | Primary database | Connection string + SSL |
| Redis | Celery broker + caching | Connection URL |

## Testing Architecture

```
pytest (1400+ tests)
├── Unit tests (70%)        → Models, serializers, utils, encryption
├── Integration tests (25%) → Views with DB, API endpoints, Celery tasks
├── Property tests (5%)     → Hypothesis-based edge case discovery
└── Mocks                   → Kafka, GCS, Gemini AI, Email, Stripe
```

Key testing boundaries:
- **Kafka**: Mocked at import time via `sys.modules` patching in `conftest.py`
- **Gemini AI**: Falls back to mock data when `GOOGLE_API_KEY` is absent
- **GCS**: Mocked via `unittest.mock.patch` on `GCSService`
- **Email**: Redirected to `locmem.EmailBackend` (autouse fixture)

## Deployment Topology (Railway)

```
Railway Project
├── Backend Service     → ai-brand-automator/ (Gunicorn)
├── Celery Worker       → ai-brand-automator/ (celery worker)
├── Celery Beat         → ai-brand-automator/ (celery beat)
├── Frontend Service    → ai-brand-automator-frontend/ (Next.js)
├── Redis               → Managed Redis instance
└── PostgreSQL          → Neon (external, SSL required)
```

CI/CD: GitHub Actions → 4 jobs (backend-tests, media-curation, frontend, build-images) → Auto-deploy on `main` merge via Railway.
