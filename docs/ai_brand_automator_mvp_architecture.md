# AI Brand Automator MVP Architecture

> **Last Updated**: 2026-01-23  
> **Version**: 2.0.0 (MVP Complete)  
> **Status**: ✅ Production Ready

## Overview
This document outlines the architecture for the AI Brand Automator MVP, a multi-tenant SaaS platform that automates brand building through AI-powered content creation, social media management, and business profile integration.

## Technical Stack (Implemented)

| Component | Technology | Status |
|-----------|------------|--------|
| **Frontend** | Next.js 15 + React 19 + TypeScript + Tailwind CSS | ✅ Implemented |
| **Backend** | Django 4.2.16 + Django REST Framework | ✅ Implemented |
| **Database** | PostgreSQL (Neon) with django-tenants | ✅ Implemented |
| **Authentication** | JWT (djangorestframework-simplejwt) | ✅ Implemented |
| **Storage** | Google Cloud Storage | ✅ Implemented |
| **Payments** | Stripe API (subscriptions) | ✅ Implemented |
| **AI Services** | Google Gemini 2.0 Flash | ✅ Implemented |
| **Message Queue** | Redis + Celery | ✅ Implemented |
| **MCP Server** | Model Context Protocol (23 tools) | ✅ Implemented |
| **Deployment** | Railway (Docker-based) | ✅ Implemented |
| **CI/CD** | GitHub Actions | ✅ Implemented |

### Social Media Integrations

| Platform | OAuth | Posting | Status |
|----------|-------|---------|--------|
| LinkedIn | ✅ | ✅ | Implemented |
| Twitter/X | ✅ | ✅ | Implemented |
| Facebook | ✅ | ✅ | Implemented |
| Instagram | ✅ | ✅ | Implemented |
| Google Business Profile | ✅ | ✅ | Implemented |

## System Architecture

### High-Level Architecture (Actual Implementation)
```
┌─────────────────┐                         ┌─────────────────┐
│   Next.js 15    │                         │   Django DRF    │
│   Frontend      │◄───── HTTPS/REST ──────►│   Backend       │
│   (Port 3000)   │                         │   (Port 8000)   │
└─────────────────┘                         └────────┬────────┘
         │                                           │
         │                                           ▼
         │                                  ┌─────────────────┐
         │                                  │   Redis         │
         │                                  │   (Broker)      │
         │                                  └────────┬────────┘
         │                                           │
         ▼                                           ▼
┌─────────────────┐    ┌─────────────────┐  ┌─────────────────┐
│  Stripe API     │    │  PostgreSQL     │  │   Celery        │
│  (Payments)     │    │  (Neon)         │  │   Worker + Beat │
└─────────────────┘    └─────────────────┘  └─────────────────┘
         │                       │                   │
         │                       │                   ▼
         │                       │          ┌─────────────────┐
         │                       │          │   MCP Server    │
         │                       │          │   (23 Tools)    │
         │                       │          └─────────────────┘
         ▼                       ▼                   │
┌─────────────────────────────────────────────────────────────┐
│                    External Services                         │
├─────────────────┬─────────────────┬─────────────────────────┤
│ Social Media    │ AI Services     │ Business Profiles       │
│ - LinkedIn      │ - Gemini 2.0    │ - Google Business       │
│ - Twitter/X     │   Flash         │   Profile (GBP)         │
│ - Facebook      │                 │                         │
│ - Instagram     │                 │                         │
└─────────────────┴─────────────────┴─────────────────────────┘
```

## Component Breakdown

### 1. Frontend (Next.js 15)
**Location**: `/ai-brand-automator-frontend`  
**Status**: ✅ Implemented

**Key Features**:
- App Router with dynamic routing
- Server Components for performance
- Client Components for interactivity
- JWT authentication with auto-refresh
- Multi-step onboarding wizard
- AI Chatbot interface
- Dashboard for content management
- Stripe checkout integration
- Subscription management page
- Social media connection UI
- Responsive design with Tailwind CSS

**Key Files**:
- `src/app/` - Page routes
- `src/components/` - Reusable components
- `src/lib/api.ts` - API client with token injection
- `src/hooks/useAuth.ts` - Authentication hook

### 2. Backend (Django REST Framework)
**Location**: `/ai-brand-automator`  
**Status**: ✅ Implemented

**Django Apps**:
| App | Purpose | Status |
|-----|---------|--------|
| `tenants` | Multi-tenancy management | ✅ |
| `onboarding` | Company onboarding workflow | ✅ |
| `ai_services` | AI chatbot and content generation | ✅ |
| `files` | File upload/management | ✅ |
| `automation` | Social media + GBP automation | ✅ |
| `subscriptions` | Stripe payment integration | ✅ |

**API Endpoints** (Actual):
- `POST /api/v1/auth/register/` - User registration
- `POST /api/v1/auth/login/` - Email-based JWT login
- `POST /api/v1/auth/refresh/` - Token refresh
- `GET/POST /api/v1/companies/` - Company CRUD
- `POST /api/v1/companies/{id}/generate_brand_strategy/` - AI generation
- `GET /api/v1/subscriptions/plans/` - List plans
- `POST /api/v1/subscriptions/create-checkout-session/` - Stripe checkout
- `POST /api/v1/subscriptions/webhook/` - Stripe webhooks
- `GET/POST /api/v1/automation/social-profiles/` - Social connections
- `GET/POST /api/v1/automation/gbp/` - Google Business Profile
- `/health/`, `/ready/`, `/alive/` - Health monitoring

### 3. Authentication (JWT-based)
**Status**: ✅ Implemented (No Kong Gateway)

**Implementation**:
- `djangorestframework-simplejwt` for JWT tokens
- Email-based login (not username)
- Django middleware for CORS (CorsMiddleware first in chain)
- Django middleware for rate limiting
- Tenant context injection via `TenantMainMiddleware`

**Authentication Flow**:
```
Client → Django (JWT Validation) → Tenant Middleware → Database (Schema)
```

### 4. Multi-Tenancy Implementation
**Status**: ✅ Implemented (MVP Mode)

**Approach**: Schema-based multi-tenancy using `django-tenants`
- Each tenant gets isolated PostgreSQL schema
- **MVP Note**: Tenant FK is nullable for simplified development
- Defensive access pattern: `tenant = getattr(request, 'tenant', None)`

**Shared Apps** (`SHARED_APPS`):
- `tenants` - Tenant management
- `ai_services` - AI service logging

**Tenant Apps** (`TENANT_APPS`):
- `onboarding` - Company data
- `files` - File management
- `automation` - Social media automation

### 5. AI Services Integration
**Status**: ✅ Implemented with Google Gemini

**AI Model**: `gemini-2.0-flash` (Google Generative AI)

**Components**:
- `GeminiAIService` - Singleton service for AI generation
- Brand strategy generation (vision, mission, values)
- Color palette suggestions
- Content generation for social media
- Logged to `AIGeneration` model with tokens/processing time

**Key Files**:
- `ai_services/services.py` - Gemini integration
- `ai_services/models.py` - AIGeneration logging

### 6. Background Processing
**Status**: ✅ Implemented

**Stack**: Celery + Redis
- **Broker**: Redis (via `CELERY_BROKER_URL`)
- **Result Backend**: Redis
- **Beat Scheduler**: For periodic tasks

**Celery Tasks** (`automation/tasks.py`):
| Task | Schedule | Purpose |
|------|----------|---------|
| `publish_scheduled_posts` | Every 60 seconds | Publish due content |
| `publish_single_post` | On-demand | Direct post publishing |

**Configuration** (`brand_automator/celery.py`):
- Auto-discovers tasks from all apps
- Beat schedule for periodic publishing

### 7. MCP Server (Model Context Protocol)
**Status**: ✅ Implemented

**Location**: `automation/mcp_server.py`  
**Transport**: stdio (Claude Desktop) or SSE (web clients)

**23 MCP Tools Available**:
| Category | Tools |
|----------|-------|
| Social Profiles | `list_social_profiles`, `get_social_profile_status`, `disconnect_social_profile` |
| Content Scheduling | `list_scheduled_content`, `create_scheduled_content`, `update_scheduled_content`, `cancel_scheduled_content`, `publish_content_now` |
| Direct Posting | `post_to_linkedin`, `post_to_twitter`, `post_to_facebook`, `post_to_instagram` |
| Google Business Profile | `create_gbp_listing`, `update_gbp_listing`, `get_gbp_listing`, `delete_gbp_listing`, `list_gbp_listings`, `create_gbp_post`, `list_gbp_posts`, `get_gbp_reviews`, `reply_to_gbp_review`, `get_gbp_insights` |
| OAuth | `get_platform_oauth_url` |
| Automation | `list_automation_tasks` |

### 8. Payment Integration (Stripe)
**Status**: ✅ Implemented

**Subscription Tiers**:
| Plan | Price | Features |
|------|-------|----------|
| Basic | $29/mo | Core features, 1 brand |
| Pro | $79/mo | Advanced AI, 5 brands, automation |
| Enterprise | $199/mo | Unlimited, team features |

**Endpoints**:
- Checkout session creation
- Subscription sync
- Billing portal
- Webhook handling (checkout, invoice, subscription events)

## Data Flow

### User Journey Flow (Implemented)
1. **Registration**: User signs up → JWT issued → User created
2. **Onboarding**: Multi-step form → Assets uploaded to GCS → Company data stored
3. **AI Generation**: Submit company data → Gemini generates brand strategy → Stored
4. **Payment**: Stripe checkout → Webhook updates subscription → Features unlocked
5. **Social Connection**: OAuth flow → Access tokens stored → Platform connected
6. **Automation**: Schedule content → Celery Beat triggers → Content published

### Authentication Flow (Actual)
```
Client → Django REST Framework → JWT Validation → Tenant Middleware → Response
       (no Kong Gateway)        (SimpleJWT)     (django-tenants)
```

## Deployment Architecture

### Development Environment
**Status**: ✅ Configured

- Docker Compose for local development (`docker-compose.yml`)
- Hot reload for frontend (Next.js dev server)
- Hot reload for backend (Django runserver)
- PostgreSQL via Neon (cloud-hosted, no local instance)
- Redis via local container or Railway

### Production Environment (Railway)
**Status**: ✅ Deployed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RAILWAY PLATFORM                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│  │  NEXT.JS    │   │   DJANGO    │   │   CELERY    │   │   CELERY    │    │
│  │  FRONTEND   │   │   BACKEND   │   │   WORKER    │   │    BEAT     │    │
│  │  (Service)  │   │  (Service)  │   │  (Service)  │   │  (Service)  │    │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘    │
│                                                                             │
│  ┌─────────────┐   ┌─────────────────────────────────────────────────┐    │
│  │ MCP SERVER  │   │                     REDIS                       │    │
│  │  (Service)  │   │              (Broker + Result Backend)          │    │
│  └─────────────┘   └─────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │   PostgreSQL    │
                              │   (Neon DB)     │
                              │   External      │
                              └─────────────────┘
```

**Railway Services**:
| Service | Dockerfile | Port |
|---------|------------|------|
| Backend | `deployment/docker/backend/Dockerfile` | 8000 |
| Frontend | `deployment/docker/frontend/Dockerfile` | 3000 |
| Celery Worker | `deployment/docker/celery-worker/Dockerfile` | - |
| Celery Beat | `deployment/docker/celery-beat/Dockerfile` | - |
| MCP Server | `deployment/docker/mcp-server/Dockerfile` | 8001 |
| Redis | Railway Redis Plugin | 6379 |

**CI/CD Pipeline** (`.github/workflows/deploy-railway.yml`):
- Automated tests on PR
- Black + Flake8 linting
- Deploy on merge to `main`
- Deploys all 5 services

## Security & Compliance

### Data Isolation
- Schema-level separation via `django-tenants`
- Nullable tenant FK for MVP flexibility
- Defensive access pattern in views

### API Security
- JWT tokens with expiration (SimpleJWT)
- CORS middleware (first in chain)
- Input validation (DRF serializers)
- Rate limiting (Django middleware)

## Implementation Phases

### Phase 1: Foundation ✅ COMPLETE
- [x] Project setup with Django + Next.js
- [x] Multi-tenancy configuration (django-tenants)
- [x] Basic authentication with JWT
- [x] Database schema design (Neon PostgreSQL)
- [x] Docker development environment

### Phase 2: Core Authentication ✅ COMPLETE
- [x] JWT authentication flow (email-based)
- [x] Tenant creation and management
- [x] User registration and login
- [x] Token refresh mechanism

### Phase 3: Onboarding System ✅ COMPLETE
- [x] Multi-step onboarding UI
- [x] File upload to Google Cloud Storage
- [x] Form validation and draft saving
- [x] Asset management interface
- [x] Company CRUD operations

### Phase 4: AI Integration ✅ COMPLETE
- [x] Chatbot UI component
- [x] Google Gemini 2.0 Flash integration
- [x] Brand strategy generation (vision, mission, values)
- [x] Color palette suggestions
- [x] AI generation logging

### Phase 5: Payment Integration ✅ COMPLETE
- [x] Stripe checkout implementation
- [x] Subscription management
- [x] Webhook handling
- [x] Feature gating based on subscription
- [x] Billing portal integration

### Phase 6: Automation Engine ✅ COMPLETE
- [x] Celery task setup (Worker + Beat)
- [x] Social media OAuth integrations (LinkedIn, Twitter, Facebook, Instagram)
- [x] Content scheduling system
- [x] Background job scheduling
- [x] MCP Server with 23 tools

### Phase 7: Advanced Features ✅ COMPLETE
- [x] Google Business Profile integration (10 MCP tools)
- [x] GBP listing CRUD
- [x] GBP post management
- [x] GBP review management
- [x] GBP insights/analytics

### Phase 8: Testing & Deployment ✅ COMPLETE
- [x] Unit tests (pytest)
- [x] Property-based tests (Hypothesis)
- [x] Integration tests
- [x] CI/CD pipeline (GitHub Actions)
- [x] Railway production deployment
- [x] Health monitoring endpoints

## Test Coverage

**Total Tests**: 226+  
**Test Framework**: pytest + Hypothesis

| App | Tests | Type |
|-----|-------|------|
| Automation | 149 | Unit, Property, Integration, Service |
| Onboarding | 30+ | Unit, Property |
| AI Services | 15+ | Unit, Integration |
| Files | 10+ | Unit |
| GBP | 77 | Unit, Property, Integration |

## Future Enhancements (Post-MVP)

### Phase 9: Video & Content Expansion (Priority: HIGH)
- [ ] YouTube video processing and optimization
- [ ] YouTube channel management integration
- [ ] Video thumbnail generation with AI
- [ ] Video transcription and captioning
- [ ] TikTok integration (OAuth + posting)
- [ ] Pinterest integration (OAuth + posting)

### Phase 10: E-commerce Integrations (Priority: HIGH)
- [ ] Shopify store connection
- [ ] Amazon seller integration
- [ ] Product catalog sync
- [ ] Inventory management
- [ ] Order notification automation
- [ ] Product listing optimization with AI

### Phase 11: Analytics & Reporting (Priority: HIGH)
- [ ] Analytics dashboard with charts (Chart.js/Recharts)
- [ ] Social media performance metrics
- [ ] GBP insights visualization
- [ ] Subscription revenue tracking
- [ ] Custom report generation
- [ ] Export to PDF/CSV

### Phase 12: Team & Collaboration (Priority: HIGH)
- [ ] User roles (Admin, Editor, Viewer)
- [ ] Team invitation system
- [ ] Role-based permissions
- [ ] Activity audit logs
- [ ] Team workspaces
- [ ] Collaborative content approval workflow

### Phase 13: Advanced AI Features (Priority: MEDIUM)
- [ ] Advanced AI chat with conversation memory
- [ ] Google Drive API file search
- [ ] Market analysis and competitor research
- [ ] AI-powered content calendar suggestions
- [ ] Sentiment analysis for reviews
- [ ] Automated response drafts for GBP reviews

### Phase 14: Marketing Integrations (Priority: MEDIUM)
- [ ] Email marketing integration (Mailchimp, SendGrid)
- [ ] SMS marketing (Twilio)
- [ ] WhatsApp Business integration
- [ ] Newsletter automation
- [ ] Lead capture forms
- [ ] CRM integration (HubSpot, Salesforce)

### Phase 15: Platform Enhancements (Priority: MEDIUM)
- [ ] Webhook management UI
- [ ] Custom domain support per tenant
- [ ] White-label customization
- [ ] API rate limiting dashboard
- [ ] Developer API documentation (Swagger/OpenAPI)
- [ ] Third-party app marketplace

### Phase 16: Mobile & Accessibility (Priority: LOW)
- [ ] Mobile app (React Native)
- [ ] Progressive Web App (PWA) support
- [ ] Push notifications
- [ ] Offline mode for content drafts
- [ ] Accessibility (WCAG 2.1 compliance)
- [ ] Internationalization (i18n) support

### Phase 17: Enterprise Features (Priority: LOW)
- [ ] SSO integration (SAML, OAuth)
- [ ] Advanced security (2FA, IP whitelisting)
- [ ] Dedicated infrastructure option
- [ ] SLA monitoring and guarantees
- [ ] Custom AI model fine-tuning
- [ ] Enterprise support portal
- [ ] Advanced reporting/exports

## Success Metrics

### Technical KPIs
- API response time < 200ms ✅ (achieved)
- 99.9% uptime ⏳ (monitoring via Railway)
- Successful AI response rate > 95% ✅ (Gemini)
- Background task completion rate > 98% ✅ (Celery)
- Test coverage: 226+ tests ✅

### Business KPIs (To Track)
- User onboarding completion rate
- Subscription conversion rate
- Monthly active users
- Customer satisfaction score

## Key Configuration Files

| File | Purpose |
|------|---------|
| `brand_automator/settings.py` | Django settings |
| `brand_automator/celery.py` | Celery configuration |
| `deployment/railway/railway.toml` | Railway deployment |
| `.github/workflows/deploy-railway.yml` | CI/CD pipeline |
| `automation/mcp_server.py` | MCP Server (23 tools) |
| `ai_services/services.py` | Gemini AI integration |

## Environment Variables

### Backend (Required)
```bash
SECRET_KEY=<django-secret>
DEBUG=False
DATABASE_URL=<neon-connection-string>
REDIS_URL=<redis-url>
GOOGLE_API_KEY=<gemini-api-key>
STRIPE_SECRET_KEY=<stripe-secret>
STRIPE_WEBHOOK_SECRET=<webhook-secret>
```

### Frontend (Required)
```bash
NEXT_PUBLIC_API_URL=<backend-url>
```

### Social OAuth (Optional per platform)
```bash
LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET
TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET
FACEBOOK_APP_ID, FACEBOOK_APP_SECRET
INSTAGRAM_CLIENT_ID, INSTAGRAM_CLIENT_SECRET
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
```

---

## Summary

The AI Brand Automator MVP is **100% complete** with:
- ✅ Full authentication system
- ✅ Multi-tenant architecture
- ✅ AI-powered brand strategy generation
- ✅ 5 social media platform integrations
- ✅ Google Business Profile management
- ✅ Stripe subscription system
- ✅ Background task processing
- ✅ MCP Server for AI agents
- ✅ Railway production deployment
- ✅ CI/CD automation

This architecture provides a solid foundation for the AI Brand Automator while allowing for future scalability and feature expansion.