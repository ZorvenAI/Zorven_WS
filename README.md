# AI Brand Automator

> **Version**: 2.0.0 (MVP Complete)  
> **Status**: ✅ Production Ready  
> **Last Updated**: January 23, 2026

**Multi-tenant SaaS platform for AI-powered brand building**

A Django REST Framework backend with Next.js frontend that helps businesses create and manage their brand strategy using Google Gemini AI.

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

### Google Business Profile (NEW ✅)
- 📍 GBP listing CRUD operations
- 📝 GBP post management
- ⭐ Review management with AI-assisted replies
- 📈 GBP insights and analytics
- 🔧 10 dedicated MCP tools

## Tech Stack

### Backend
- **Django 4.2.16** + Django REST Framework
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
- **Railway** for production hosting
- **Docker** for containerization
- **GitHub Actions** for CI/CD
- **241+ tests** (pytest + Hypothesis)

## Project Structure

```
.
├── ai-brand-automator/          # Django backend
│   ├── ai_services/             # AI integration & chat (Gemini 2.0 Flash)
│   ├── automation/              # Social media automation & MCP server
│   │   ├── docs/                # Platform integration documentation
│   │   ├── mcp_server.py        # MCP Server with 23 tools
│   │   ├── models.py            # SocialProfile, ContentCalendar, GBP models
│   │   ├── services.py          # Platform API services
│   │   ├── tasks.py             # Celery background tasks
│   │   └── views.py             # OAuth & posting endpoints (5700+ lines)
│   ├── files/                   # File upload service
│   ├── onboarding/              # Company onboarding
│   ├── subscriptions/           # Stripe subscription management
│   ├── tenants/                 # Multi-tenancy models
│   └── brand_automator/         # Django settings & Celery config
│
├── ai-brand-automator-frontend/ # Next.js frontend
│   └── src/
│       ├── app/                 # Next.js pages
│       │   ├── automation/      # Social media automation page
│       │   ├── dashboard/       # Main dashboard
│       │   └── subscription/    # Billing management
│       ├── components/          # React components
│       ├── hooks/               # Custom hooks (useAuth)
│       └── lib/                 # API client & utilities
│
├── deployment/                  # Railway deployment configs
│   ├── docker/                  # Dockerfiles for all services
│   │   ├── kong/                # Kong Gateway (DB-less mode)
│   │   │   ├── kong.yaml        # Declarative configuration
│   │   │   └── Dockerfile       # Kong container
│   │   └── ...                  # Other service Dockerfiles
│   └── railway/                 # Railway configuration
│
├── .github/workflows/           # CI/CD pipelines
│   └── deploy-railway.yml       # Full deployment pipeline
│
└── docs/                        # Architecture documentation
    ├── ai_brand_automator_mvp_architecture.md
    └── CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md
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

### Docker Quick Start (with Kong Gateway)

For full-stack development with Kong Gateway, Kafka, and all services:

```bash
cd ai-brand-automator

# Start core services (Kong, Django, Redis, PostgreSQL)
docker-compose up -d

# Or include Kafka for event streaming
docker-compose --profile with-kafka up -d

# Verify services are running
curl http://localhost:8000/health/   # Via Kong
curl http://localhost:8002/status    # Kong Admin API
```

**Port mapping with Kong:**
| Service | Port | Description |
|---------|------|-------------|
| Kong Gateway | 8000 | Main API entry point |
| Django Backend | 8001 | Internal (via Kong only) |
| Kong Admin | 8002 | Gateway config/debug |
| MCP Server | 8003 | AI agent tools |
| Frontend | 3000 | Next.js |

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

## User Flow

1. **Registration** → Create account + tenant
2. **Onboarding Step 1** → Company information
3. **Onboarding Step 2** → Brand details
4. **Onboarding Step 3** → Target audience
5. **Onboarding Step 4** → Upload assets (optional)
6. **Onboarding Step 5** → Review & generate brand strategy with AI
7. **Dashboard** → View metrics and recent activity
8. **Chat** → Interact with AI for brand guidance
9. **Automation** → Connect LinkedIn, create and schedule posts

## Development

### Running Tests

**Backend**:
```bash
cd ai-brand-automator
source ../.venv/bin/activate
pytest -v                      # All tests (226+)
pytest -m unit                 # Unit tests only
pytest -m property             # Property-based tests (Hypothesis)
pytest automation/tests/ -v    # Automation tests (149)
pytest --cov=. --cov-report=html  # With coverage
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
- Data is isolated in separate PostgreSQL schemas
- `PUBLIC_SCHEMA_NAME = 'public'` for shared data
- `TENANT_MODEL = 'tenants.Tenant'`
- `TENANT_DOMAIN_MODEL = 'tenants.Domain'`

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

## License

See [LICENSE.md](docs/LICENSE.md)

## Status

**Current Version**: 2.0.0 (MVP Complete)  
**Status**: ✅ Production Ready  
**Deployment**: Railway  
**Last Updated**: January 23, 2026

### Test Coverage
| Component | Tests | Status |
|-----------|-------|--------|
| Automation | 149 | ✅ |
| GBP | 77 | ✅ |
| Onboarding | 30+ | ✅ |
| AI Services | 15+ | ✅ |
| Files | 10+ | ✅ |
| **Total** | **226+** | ✅ |

### Completed Features (MVP)
- ✅ Multi-tenant authentication
- ✅ User registration with tenant creation
- ✅ 5-step onboarding flow
- ✅ AI brand strategy generation (Gemini 2.0 Flash)
- ✅ AI brand identity with color palettes
- ✅ Dynamic dashboard
- ✅ Token refresh
- ✅ File upload UI
- ✅ Chat interface
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
- ✅ CI/CD with GitHub Actions
- ✅ 226+ automated tests

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
- Phase 11: Analytics & Reporting
- Phase 12: Team & Collaboration
- Phase 13-17: Advanced AI, Marketing, Enterprise features
