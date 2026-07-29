#!/usr/bin/env python3
"""
Create GitHub issues for AI Brand Automator codebase fixes - ALL 63 ISSUES
"""

import subprocess
import time

ISSUES = [
    # ===== CRITICAL ISSUES (4) =====
    {
        "title": "🔴 C-01: Multi-tenancy middleware enabled but broken",
        "body": """**Priority**: BLOCKING | **Time**: 8-12 hours | **Dependencies**: None

## Problem
`TenantMainMiddleware` is in MIDDLEWARE list but tenant system is disabled. Every request tries to resolve `request.tenant` and fails with AttributeError.

## Impact
ALL API requests fail - application is non-functional

## Fix
Enable full multi-tenancy (Option B approved):
1. Configure SHARED_APPS and TENANT_APPS properly
2. Set DATABASE_ROUTERS for schema isolation
3. Configure TENANT_MODEL and TENANT_DOMAIN_MODEL
4. Implement domain routing logic
5. Test tenant resolution

**Location**: `brand_automator/settings.py` Line 73, 23+ references to `request.tenant`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🔴 C-02: No user registration endpoint",
        "body": """**Priority**: BLOCKING | **Time**: 4-6 hours | **Depends on**: #1

## Problem
Missing `POST /api/v1/auth/register/` endpoint. Users cannot create accounts.

## Impact
Cannot create accounts - application unusable

## Fix
1. Create UserRegistrationSerializer with validation
2. Create UserRegistrationView
3. Create tenant schema on registration
4. Return JWT tokens (access + refresh)
5. Wire up URL route

**Location**: `brand_automator/urls.py`, Frontend: `RegisterForm.tsx` Line 30

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🔴 C-03: JWT login email/username mismatch",
        "body": """**Priority**: BLOCKING | **Time**: 2-3 hours | **Dependencies**: None

## Problem
JWT expects `username`, frontend sends `email`. All logins fail with 400 Bad Request.

## Impact
Users cannot login - authentication broken

## Fix
Create custom `EmailTokenObtainPairSerializer` with `username_field = 'email'`

```python
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'
```

**Location**: Frontend `LoginForm.tsx` Line 17, Backend JWT configuration

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🔴 C-04: No tenant creation workflow",  
        "body": """**Priority**: BLOCKING | **Time**: 3-4 hours | **Depends on**: #1, #2

## Problem
Company creation fails due to missing tenant foreign key. No mechanism to create Tenant records for new users.

## Impact
Company creation fails - onboarding broken

## Fix
1. Create tenant during user registration (schema_name = f'tenant_{user.id}')
2. Update CompanyViewSet.perform_create() to use `request.tenant`
3. Auto-create OnboardingProgress with tenant reference
4. Ensure tenant exists before Company save

**Location**: `onboarding/views.py` Line 36, `onboarding/models.py` Line 7

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    
    # ===== HIGH PRIORITY ISSUES (20) =====
    {
        "title": "🟠 H-01: Foreign key constraint violations on tenant fields",
        "body": """**Priority**: HIGH | **Time**: 2-3 hours | **Depends on**: #1

## Problem
All models reference Tenant foreign key but tenant system is disabled. Migrations and model saves will fail.

## Locations
- `onboarding/models.py` Line 7: `Company.tenant = OneToOneField(Tenant)`
- `onboarding/models.py` Line 39: `BrandAsset.tenant = ForeignKey(Tenant)`
- `ai_services/models.py` Line 7: `ChatSession.tenant = ForeignKey(Tenant)`

## Fix
After enabling multi-tenancy, ensure all tenant FKs work correctly. Add tests for tenant isolation.

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-02: Database credentials exposed in source code",
        "body": """**Priority**: HIGH | **Time**: 1 hour | **Dependencies**: None

## ⚠️ SECURITY ISSUE
A database password is hardcoded in settings.py Lines 103-109 (value redacted here — see Neon dashboard)

## Immediate Actions
1. **URGENT**: Rotate database password in Neon dashboard
2. Move all credentials to .env file
3. Create .env.example template
4. Update .gitignore to exclude .env
5. Never commit .env to Git

**Location**: `brand_automator/settings.py` Lines 103-109

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-03: SECRET_KEY exposed with insecure default",
        "body": """**Priority**: HIGH | **Time**: 15 min | **Dependencies**: None

## Problem
Default fallback SECRET_KEY is insecure Django dev key, committed to repository

## Fix
Generate new SECRET_KEY and move to environment variable:

```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Add to .env, remove default fallback from settings.py

**Location**: `settings.py` Line 24

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-04: File upload endpoint has hardcoded company ID",
        "body": """**Priority**: HIGH | **Time**: 2-3 hours | **Depends on**: #1

## Problem
Line 124: `company = get_object_or_404(Company, pk=1)` - hardcoded company ID
- No tenant filtering
- GCS upload commented out (Line 130)

## Impact
File uploads only work for company ID=1, returns mock URLs

## Fix
- Get company from request.user or URL parameter
- Filter by tenant: `request.tenant.company`
- Enable real GCS upload

**Location**: `onboarding/views.py` Lines 124-126

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-05: AI service tenant logging fails",
        "body": """**Priority**: HIGH | **Time**: 1-2 hours | **Depends on**: #1

## Problem
`AIGeneration.objects.create(tenant=company_data.get('tenant'))` - tenant value is object or None, not validated

## Impact
Foreign key constraint violation when logging AI generations

## Fix
Validate tenant value or extract properly from request context

**Location**: `ai_services/services.py` Line 76

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-06: Missing GCS configuration",
        "body": """**Priority**: HIGH | **Time**: 3-4 hours | **Dependencies**: None

## Problem
All GCS settings default to empty strings. File uploads return mock URLs instead of storing files.

## Fix
1. Create GCS bucket in Google Cloud
2. Create service account with Storage Admin role
3. Download JSON key file
4. Configure environment variables:
   - `GS_BUCKET_NAME`
   - `GS_PROJECT_ID`
   - `GS_CREDENTIALS_PATH`
5. Test file upload/download

**Location**: `settings.py` Lines 197-199

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-07: Missing authentication decorators on API views",
        "body": """**Priority**: HIGH | **Time**: 30 min | **Dependencies**: None

## ⚠️ SECURITY ISSUE
ai_services/views.py endpoints don't require authentication - unauthenticated users can access AI endpoints

## Fix
Add `@permission_classes([IsAuthenticated])` to all protected API views:
- Lines 46, 97, 137, 177 in `ai_services/views.py`

**Location**: `ai_services/views.py` Lines 46, 97, 137, 177

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-08: OnboardingProgress auto-creation fails",
        "body": """**Priority**: HIGH | **Time**: 1 hour | **Depends on**: #1, #4

## Problem
Company save fails without tenant, then `OnboardingProgress.objects.create(tenant=company.tenant)` tries to access non-existent tenant

## Impact
Company creation fails - onboarding broken

## Fix
Fix tenant handling in `CompanyViewSet.perform_create()` to properly pass tenant from request

**Location**: `onboarding/views.py` Lines 35-40

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-09: Chat session creation fails",
        "body": """**Priority**: HIGH | **Time**: 1 hour | **Depends on**: #1

## Problem
`ChatSession.objects.create()` fails due to missing `request.tenant`

## Impact
Chat functionality completely broken

## Fix
Remove tenant dependency or properly implement tenant context in chat views

**Location**: `ai_services/views.py` Lines 55-61

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-10: Missing error handling in AI service",
        "body": """**Priority**: HIGH | **Time**: 3-4 hours | **Dependencies**: None

## Problems
- No validation if API key is None
- Silent fallback hides errors
- No logging for exceptions
- No retry logic for transient failures

## Impact
AI failures silently return mock data, debugging is difficult

## Fix
Add proper error handling, structured logging, API key validation, and retry logic to GeminiAIService

**Location**: `ai_services/services.py`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#21-backend-django-issues-25-issues)"""
    },
    {
        "title": "🟠 H-11: Missing component exports (TypeScript errors)",
        "body": """**Priority**: HIGH | **Time**: 15 min | **Dependencies**: None

## Problem
Missing `export` keywords on interfaces. Frontend doesn't compile.

## Locations
- `components/chat/MessageBubble.tsx` - Missing `export` on Message and MessageBubbleProps
- `components/chat/FileSearch.tsx` - Missing `export` on interfaces

## Error
"Cannot find module './MessageBubble' or its corresponding type declarations"

## Fix
Add `export` keyword to all interface declarations

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#22-frontend-nextjs-issues-13-issues)"""
    },
    {
        "title": "🟠 H-12: Field name mismatches (camelCase vs snake_case)",
        "body": """**Priority**: HIGH | **Time**: 2-3 hours | **Dependencies**: None

## Problem
Frontend sends camelCase: `{targetAudience: '', coreProblem: ''}`
Backend expects snake_case: `target_audience`, `core_problem`

## Impact
Backend receives empty values - data is lost on save

## Fix
Option 1: Convert in serializer with field aliases
Option 2: Update frontend to send snake_case

**Location**: `components/onboarding/CompanyForm.tsx`, `onboarding/models.py`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#22-frontend-nextjs-issues-13-issues)"""
    },
    {
        "title": "🟠 H-13: API client missing comprehensive error handling",
        "body": """**Priority**: HIGH | **Time**: 2-3 hours | **Dependencies**: None

## Problems
- Only handles 401 status
- No handling for 400, 403, 500 errors
- No retry logic for network failures
- No response body parsing helpers

## Impact
Poor error messages, no recovery from transient failures

## Fix
Add comprehensive error handling for all HTTP status codes and implement retry logic

**Location**: `lib/api.ts`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#22-frontend-nextjs-issues-13-issues)"""
    },
    {
        "title": "🟠 H-14: Missing authentication guards on protected pages",
        "body": """**Priority**: HIGH | **Time**: 1-2 hours | **Dependencies**: None

## ⚠️ SECURITY ISSUE
No JWT token check on dashboard, chat, onboarding pages - unauthenticated users can access

## Fix
Create `useAuth()` hook:
- Check for token in localStorage
- Redirect to /auth/login if missing
- Add to all protected pages

**Location**: All page components (dashboard, chat, onboarding)

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#22-frontend-nextjs-issues-13-issues)"""
    },
    {
        "title": "🟠 H-15: Hardcoded company ID fallback in BrandForm",
        "body": """**Priority**: HIGH | **Time**: 30 min | **Dependencies**: None

## Problem
Line 29: `const companyId = localStorage.getItem('company_id') || '1'`

Dangerous fallback - user might update wrong company's data

## Fix
Show error if company_id not found, don't fallback to '1'

**Location**: `components/onboarding/BrandForm.tsx` Line 29

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#22-frontend-nextjs-issues-13-issues)"""
    },
    {
        "title": "🟠 H-16: Missing onboarding steps 3-5",
        "body": """**Priority**: HIGH | **Time**: 8 hours | **Dependencies**: None

## Problem
Only step-1 (company info) and step-2 (brand details) exist. StepWizard shows 5 steps.

## Missing
- step-3: Brand strategy generation
- step-4: Brand identity generation
- step-5: Review and submit

## Impact
Users cannot complete onboarding flow

## Fix
Implement remaining 3 steps with proper UI and API integration

**Location**: `app/onboarding/` directory

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#22-frontend-nextjs-issues-13-issues)"""
    },
    {
        "title": "🟠 H-17: Dashboard data is static",
        "body": """**Priority**: HIGH | **Time**: 4 hours | **Dependencies**: None

## Problem
All dashboard data is hardcoded - no API calls to fetch real data

## Impact
Dashboard shows fake data, not useful to users

## Fix
Create dashboard API endpoints and integrate with real user data

**Location**: `components/dashboard/OverviewCards.tsx`, `RecentActivity.tsx`, `QuickActions.tsx`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#22-frontend-nextjs-issues-13-issues)"""
    },
    {
        "title": "🟠 H-18: No token refresh logic",
        "body": """**Priority**: HIGH | **Time**: 2 hours | **Dependencies**: None

## Problem
No automatic token refresh - users logged out after 60 minutes (access token expiry)

## Fix
Implement automatic token refresh before expiry:
- Check token expiration
- Use refresh_token to get new access_token
- Handle refresh token expiry

**Location**: `lib/api.ts`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#22-frontend-nextjs-issues-13-issues)"""
    },
    {
        "title": "🟠 H-19: Brand strategy generation UI missing",
        "body": """**Priority**: HIGH | **Time**: 3 hours | **Dependencies**: None

## Problem
Backend has `POST /api/v1/companies/{id}/generate_brand_strategy/` but no UI trigger

## Impact
Users cannot initiate brand strategy generation

## Fix
Add button/form in onboarding step-3 to trigger generation, display results

**Location**: Frontend onboarding flow

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟠 H-20: Brand identity generation UI missing",
        "body": """**Priority**: HIGH | **Time**: 3 hours | **Dependencies**: None

## Problem
Backend has `POST /api/v1/ai/generate-brand-identity/` but no UI

## Impact
Users cannot generate brand identity

## Fix
Add UI in onboarding step-4 for brand identity generation

**Location**: Frontend onboarding flow

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    
    # ===== MEDIUM PRIORITY ISSUES (25) =====
    {
        "title": "🟡 M-01: No request validation middleware",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

No centralized request validation - invalid data can reach business logic

## Fix
Add validation middleware or use DRF validators consistently across all views

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-02: Missing password strength validation",
        "body": """**Priority**: MEDIUM | **Time**: 1 hour

No enforcement of password complexity - weak passwords allowed

## Fix
Add password validators: min length 8, upper/lower/digit/special char requirements

**Location**: User registration

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-03: No email verification",
        "body": """**Priority**: MEDIUM | **Time**: 4 hours

Email addresses not verified - fake emails can register

## Fix
Send verification email with token, verify before allowing full access

**Location**: Registration flow

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-04: Missing rate limiting",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

No rate limiting configured - vulnerable to brute force attacks

## Fix
Add django-ratelimit or DRF throttling to authentication and API endpoints

**Location**: All API endpoints

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-05: No API response pagination",
        "body": """**Priority**: MEDIUM | **Time**: 1 hour

All records returned at once - performance issues with large datasets

## Fix
Add DRF pagination (PageNumberPagination) to list endpoints

**Location**: List endpoints (companies, chat sessions, etc.)

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-06: Missing database indexes",
        "body": """**Priority**: MEDIUM | **Time**: 1 hour

No indexes on frequently queried fields - slow queries as data grows

## Fix
Add `db_index=True` to: email, created_at, tenant_id, and other frequently queried fields

**Location**: Model definitions

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-07: No query optimization",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

No `select_related` or `prefetch_related` - N+1 query problem

## Fix
Add query optimization to viewsets with foreign key access

**Location**: Views with foreign key traversal

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-08: Missing logging configuration",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

No structured logging configured - difficult to debug production issues

## Fix
Configure logging with handlers, formatters, and log levels (INFO, WARNING, ERROR)

**Location**: `settings.py`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-09: No error tracking",
        "body": """**Priority**: MEDIUM | **Time**: 1 hour

No Sentry or error tracking integration - production errors go unnoticed

## Fix
Integrate Sentry for error tracking and monitoring

**Location**: Backend

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-10: Hardcoded frontend API URLs",
        "body": """**Priority**: MEDIUM | **Time**: 30 min

Some files use `http://localhost:8000` instead of environment variable

## Fix
Ensure all API calls use `process.env.NEXT_PUBLIC_API_URL`

**Location**: Various frontend components

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-11: No loading states",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

No loading spinners during API calls - poor UX

## Fix
Add loading state management and UI indicators (spinners, skeletons)

**Location**: Most frontend components

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-12: No error boundaries",
        "body": """**Priority**: MEDIUM | **Time**: 1 hour

No React error boundaries - whole app crashes on component errors

## Fix
Add error boundary components to catch and display errors gracefully

**Location**: Frontend app

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-13: Missing form validation messages",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

Generic error messages - users don't know what to fix

## Fix
Add specific validation messages for each field with clear guidance

**Location**: Forms without proper validation feedback

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-14: No accessibility (a11y) attributes",
        "body": """**Priority**: MEDIUM | **Time**: 4 hours

Missing ARIA labels, semantic HTML - not accessible to screen readers

## Fix
Add proper ARIA attributes and semantic HTML to all components

**Location**: Frontend components

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-15: Missing toast notifications",
        "body": """**Priority**: MEDIUM | **Time**: 1 hour

No global notification system - users miss success/error feedback

## Fix
Add toast notification library (react-hot-toast or similar)

**Location**: Frontend

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-16: No file type validation",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

Only checks MIME type - malicious files could be uploaded

## Fix
Add server-side file validation, virus scanning, content verification

**Location**: File upload endpoint

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-17: Missing file size limits",
        "body": """**Priority**: MEDIUM | **Time**: 30 min

No max file size enforced - large files can consume storage/bandwidth

## Fix
Add file size validation (e.g., 10MB limit) on backend and frontend

**Location**: File upload

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-18: No image optimization",
        "body": """**Priority**: MEDIUM | **Time**: 3 hours

Images uploaded as-is - large files slow down loading

## Fix
Add image compression/optimization on upload (resize, compress)

**Location**: File upload

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-19: Missing alt text for images",
        "body": """**Priority**: MEDIUM | **Time**: 1 hour

No alt text on img tags - poor accessibility

## Fix
Add meaningful alt text to all images

**Location**: Frontend components with images

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-20: No caching strategy",
        "body": """**Priority**: MEDIUM | **Time**: 4 hours

No caching for expensive queries - slow response times

## Fix
Add Redis caching for AI responses, static data, and frequently accessed queries

**Location**: Backend API

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-21: Missing API documentation",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

No Swagger/OpenAPI docs - frontend developers must read source code

## Fix
Add drf-spectacular for auto-generated API documentation

**Location**: Backend

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-22: No Docker configuration",
        "body": """**Priority**: MEDIUM | **Time**: 4 hours

No Dockerfile or docker-compose.yml - inconsistent development environments

## Fix
Create Docker configurations for backend, frontend, and database

**Location**: Project root

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#24-missing-implementations-8-issues)"""
    },
    {
        "title": "🟡 M-23: Missing CI/CD pipeline",
        "body": """**Priority**: MEDIUM | **Time**: 4 hours

No GitHub Actions for testing/deployment - manual testing required

## Fix
Create CI/CD workflow for automated tests and deployment

**Location**: `.github/workflows`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#26-configuration-issues-4-issues)"""
    },
    {
        "title": "🟡 M-24: No environment-specific settings",
        "body": """**Priority**: MEDIUM | **Time**: 2 hours

Single settings file for all environments - dev/staging/prod mixed

## Fix
Split into settings_dev.py, settings_staging.py, settings_prod.py

**Location**: `settings.py`

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#26-configuration-issues-4-issues)"""
    },
    {
        "title": "🟡 M-25: Missing backup strategy",
        "body": """**Priority**: MEDIUM | **Time**: 1 hour

No automated backups configured - data loss risk

## Fix
Configure Neon automated backups or implement backup script

**Location**: Database

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#26-configuration-issues-4-issues)"""
    },
    
    # ===== LOW PRIORITY ISSUES (14) =====
    # Infrastructure Issues
    {
        "title": "🟢 I-01: API endpoint mismatches",
        "body": """**Priority**: LOW | **Time**: 2 hours

Frontend calls don't match backend endpoints exactly

## Issues
- Login expects username not email
- Missing register endpoint
- Tenant requirements not met

## Fix
See detailed table in analysis document

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#23-integration-issues-6-issues)"""
    },
    {
        "title": "🟢 I-02: Missing CORS headers",
        "body": """**Priority**: LOW | **Time**: 15 min

`CORS_ALLOW_CREDENTIALS = True` but no `CORS_ALLOW_HEADERS` configured

## Fix
Add `CORS_ALLOW_HEADERS = ['authorization', 'content-type']`

**Location**: `settings.py` Line 125

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#23-integration-issues-6-issues)"""
    },
    {
        "title": "🟢 I-03: Inconsistent response format",
        "body": """**Priority**: LOW | **Time**: 2 hours

Some endpoints return `{data: {...}}`, others return data directly

## Fix
Standardize all responses to consistent format

**Location**: Various API endpoints

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#23-integration-issues-6-issues)"""
    },
    {
        "title": "🟢 I-04: Missing API versioning",
        "body": """**Priority**: LOW | **Time**: 1 hour

Not all endpoints under `/api/v1/` prefix

## Fix
Ensure all endpoints follow versioning pattern

**Location**: URL structure

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#23-integration-issues-6-issues)"""
    },
    {
        "title": "🟢 I-05: No WebSocket support",
        "body": """**Priority**: LOW | **Time**: 8 hours

Chat uses polling instead of WebSocket - inefficient, high latency

## Fix
Implement Django Channels for real-time chat

**Location**: Chat feature

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#23-integration-issues-6-issues)"""
    },
    {
        "title": "🟢 I-06: Missing health check endpoint",
        "body": """**Priority**: LOW | **Time**: 30 min

No `/health` or `/ping` endpoint - load balancers can't check application health

## Fix
Add health check endpoint returning 200 OK with system status

**Location**: Backend

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#23-integration-issues-6-issues)"""
    },
    # Security Issues (duplicates noted in analysis)
    {
        "title": "🟢 S-03: No CSRF protection",
        "body": """**Priority**: LOW | **Time**: 1 hour

Frontend doesn't include CSRF tokens - CSRF attacks possible

## Fix
Configure DRF CSRF exemption for JWT or add CSRF tokens to requests

**Location**: Frontend API calls

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#25-security-issues-5-issues)"""
    },
    {
        "title": "🟢 S-04: File upload without validation",
        "body": """**Priority**: LOW | **Time**: 4 hours

No virus scanning, malware detection - malicious files could be uploaded

## Fix
Add antivirus scanning, content validation, sanitization

**Location**: File upload endpoint

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#25-security-issues-5-issues)"""
    },
    {
        "title": "🟢 S-05: Prompt injection risk",
        "body": """**Priority**: LOW | **Time**: 2 hours

User input directly embedded in AI prompts - users could manipulate AI responses

## Fix
Sanitize user input, add prompt injection detection

**Location**: AI service

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#25-security-issues-5-issues)"""
    },
    # Configuration Issues
    {
        "title": "🟢 CF-01: Missing environment variables documentation",
        "body": """**Priority**: LOW | **Time**: 30 min

Required environment variables not documented

## Fix
Document all required env vars in README

**Missing**: SECRET_KEY, DEBUG, DATABASE_URL, GOOGLE_API_KEY, GCS vars, NEXT_PUBLIC_API_URL

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#26-configuration-issues-4-issues)"""
    },
    {
        "title": "🟢 CF-02: No .env.example file",
        "body": """**Priority**: LOW | **Time**: 15 min

No template for environment variables

## Fix
Create .env.example in both backend and frontend with all required variables

**Location**: Project root

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#26-configuration-issues-4-issues)"""
    },
    {
        "title": "🟢 CF-03: No requirements-dev.txt",
        "body": """**Priority**: LOW | **Time**: 15 min

Dev dependencies missing - inconsistent dev tooling

## Fix
Create requirements-dev.txt with pytest, black, flake8, mypy, etc.

**Location**: Backend

See: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#26-configuration-issues-4-issues)"""
    },
    # Testing Issues
    {
        "title": "🟢 T-01: Zero backend tests",
        "body": """**Priority**: LOW | **Time**: 20 hours

All tests.py files are empty - no test coverage

## Fix
Implement pytest test suite with 70% coverage target

See Phase 3: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#54-phase-3-testing--quality-week-4)"""
    },
    {
        "title": "🟢 T-02: Zero frontend tests",
        "body": """**Priority**: LOW | **Time**: 15 hours

No Jest config, no tests - no frontend coverage

## Fix
Set up Jest + RTL, create component tests, target 60% coverage

See Phase 3: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#54-phase-3-testing--quality-week-4)"""
    },
    
    # ===== META TRACKING ISSUES (3) =====
    {
        "title": "📋 [META] Phase 1: Critical Fixes Tracking",
        "body": """Track completion of all 4 critical blocking issues.

**Checklist**:
- [ ] #1 - C-01: Multi-tenancy enabled
- [ ] #2 - C-02: User registration
- [ ] #3 - C-03: JWT login fixed  
- [ ] #4 - C-04: Tenant creation workflow

**Goal**: Application becomes functional  
**Timeline**: Week 1 (~15 hours)  
**Status**: Not started

See full plan: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#52-phase-1-critical-fixes-week-1)"""
    },
    {
        "title": "📋 [META] Phase 2: High Priority Fixes Tracking",
        "body": """Track completion of all 20 high priority issues.

**Checklist**:
- [ ] #5 - H-01 through #24 - H-20 (all high priority issues)

**Goal**: Core features working  
**Timeline**: Week 2-3 (~30 hours)  
**Status**: Blocked by Phase 1

See full plan: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#53-phase-2-core-features-week-2-3)"""
    },
    {
        "title": "📋 [META] Phase 3: Testing Implementation Tracking",
        "body": """Track test suite implementation.

**Checklist**:
- [ ] Backend test setup (pytest, fixtures, coverage)
- [ ] Backend unit tests (70% coverage target)
- [ ] Backend integration tests
- [ ] Frontend test setup (Jest, Testing Library)
- [ ] Frontend component tests (60% coverage)
- [ ] E2E tests (optional)

**Timeline**: Week 4 (~43 hours)  
**Status**: Blocked by Phase 2

See full plan: [CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md](CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md#54-phase-3-testing--quality-week-4)"""
    }
]

def create_issue(title, body):
    """Create a single GitHub issue"""
    try:
        result = subprocess.run(
            ['gh', 'issue', 'create', '--title', title, '--body', body],
            capture_output=True,
            text=True,
            check=True
        )
        issue_url = result.stdout.strip()
        issue_num = issue_url.split('/')[-1] if issue_url else '?'
        print(f"✅ Created #{issue_num}: {title}")
        return issue_num
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create: {title}")
        print(f"   Error: {e.stderr}")
        return None

def main():
    print("🚀 Creating ALL 63 GitHub issues for AI Brand Automator...\n")
    print(f"📊 Total issues to create: {len(ISSUES)}")
    print("   🔴 Critical: 4")
    print("   🟠 High Priority: 20") 
    print("   🟡 Medium Priority: 25")
    print("   🟢 Low Priority: 14")
    print("   📋 Meta Tracking: 3\n")
    
    created = []
    failed = []
    
    for i, issue in enumerate(ISSUES, 1):
        print(f"[{i}/{len(ISSUES)}] Creating: {issue['title'][:60]}...")
        issue_num = create_issue(issue['title'], issue['body'])
        
        if issue_num:
            created.append(issue_num)
        else:
            failed.append(issue['title'])
        
        # Rate limit: 1 second between requests
        if i < len(ISSUES):
            time.sleep(1)
    
    print(f"\n{'='*60}")
    print(f"✅ Successfully created {len(created)} issues")
    if failed:
        print(f"❌ Failed to create {len(failed)} issues:")
        for title in failed:
            print(f"   - {title}")
    print(f"{'='*60}\n")
    
    print("View all issues: gh issue list")
    print("See full details: CODEBASE_ANALYSIS_AND_IMPLEMENTATION_PLAN.md")

if __name__ == '__main__':
    main()
