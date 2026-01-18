# AI Brand Automator

**Multi-tenant SaaS platform for AI-powered brand building**

A Django REST Framework backend with Next.js frontend that helps businesses create and manage their brand strategy using Google Gemini AI.

## Features

- 🔐 **Multi-tenant Architecture** - Schema-based data isolation with django-tenants
- 🤖 **AI Brand Strategy Generation** - Powered by Google Gemini 2.0 Flash
- 📝 **5-Step Onboarding** - Guided company setup with asset uploads
- 💬 **AI Chatbot** - Interactive brand guidance and file search
- 📊 **Dynamic Dashboard** - Real-time metrics and activity tracking
- 🔄 **Auto Token Refresh** - Seamless 7-day authentication
- 📁 **File Upload** - Multi-file drag-and-drop with GCS integration
- 💳 **Stripe Integration** - Subscription plans with checkout and billing portal
- 📱 **Mobile Ready** - Responsive design with network testing support
- 🔗 **LinkedIn Integration** - OAuth 2.0 with posting, scheduling, analytics & webhooks
- 🐦 **Twitter/X Integration** - OAuth 2.0 with PKCE, threads, media uploads, analytics
- 📘 **Facebook Integration** - Page posting, stories, carousels, resumable video uploads
- 📅 **Content Calendar** - Schedule and manage social media posts across platforms
- ⚡ **Celery Automation** - Background task processing for scheduled posts
- 🖼️ **Media Attachments** - Images, videos, documents with platform-specific limits
- 💾 **Draft Save/Restore** - Auto-save drafts with media support in compose modals
- 📊 **Social Analytics** - Engagement metrics and insights for all platforms

## Tech Stack

### Backend
- **Django 4.2** + Django REST Framework
- **PostgreSQL** (Neon hosted) with multi-tenancy
- **Google Gemini 2.0 Flash** for AI content generation
- **Stripe** for subscription management
- **Celery 5.6** + Redis for background task processing
- **JWT Authentication** with token refresh

### Frontend
- **Next.js 15** + React 19
- **TypeScript** for type safety
- **Tailwind CSS** for styling
- **Automatic API client** with token management

## Project Structure

```
.
├── ai-brand-automator/          # Django backend
│   ├── ai_services/             # AI integration & chat
│   ├── automation/              # Social media automation & LinkedIn
│   │   ├── docs/                # Integration documentation
│   │   ├── models.py            # SocialProfile, ContentCalendar
│   │   ├── services.py          # LinkedIn API service
│   │   ├── tasks.py             # Celery background tasks
│   │   └── views.py             # OAuth & posting endpoints
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
└── docs/                        # Architecture documentation
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
- `GET /api/v1/automation/linkedin/connect/` - Initiate LinkedIn OAuth
- `GET /api/v1/automation/linkedin/callback/` - OAuth callback handler
- `POST /api/v1/automation/linkedin/test-connect/` - Test mode connection (DEBUG only)
- `POST /api/v1/automation/linkedin/disconnect/` - Disconnect LinkedIn account
- `POST /api/v1/automation/linkedin/post/` - Post to LinkedIn immediately
- `POST /api/v1/automation/linkedin/media/upload/` - Upload image, video, or document
- `GET /api/v1/automation/linkedin/video/status/{urn}/` - Check video processing status
- `GET /api/v1/automation/linkedin/document/status/{urn}/` - Check document processing status
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
pytest  # (to be implemented)
```

**Frontend**:
```bash
cd ai-brand-automator-frontend
npm test  # (to be implemented)
```

### Code Quality

**Backend**:
```bash
python manage.py check  # Django system check
```

**Frontend**:
```bash
npm run build  # TypeScript compilation check
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

- [Architecture Plan](plans/ai_brand_automator_mvp_plan.md)
- [Codebase Analysis](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md)
- [Copilot Instructions](.github/copilot-instructions.md)

## License

See [LICENSE.md](LICENSE.md)

## Status

**Current Version**: MVP 1.2  
**Status**: ✅ Production Ready  
**Last Updated**: January 15, 2026

### Completed Features
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
- ✅ LinkedIn OAuth integration with token encryption
- ✅ Immediate LinkedIn posting
- ✅ Content Calendar with scheduling
- ✅ Edit scheduled posts
- ✅ Media attachments (images, videos, documents)
- ✅ Celery-based automatic publishing (every 5 minutes)
- ✅ Published posts history with configurable limit
- ✅ Automation tasks view with status badges
- ✅ Test mode for LinkedIn development

### LinkedIn Media Specifications
| Media Type | Max Size | Formats |
|------------|----------|---------|
| Image | 8MB | JPEG, PNG, GIF |
| Video | 500MB | MP4 only |
| Document | 100MB | PDF, DOC, DOCX, PPT, PPTX |

### Pending Features (Post-MVP)
- ⏳ Twitter/X integration
- ⏳ Instagram integration
- ⏳ Facebook integration
- ⏳ Media attachments in posts
- ⏳ Advanced analytics
- ⏳ Team member invites
