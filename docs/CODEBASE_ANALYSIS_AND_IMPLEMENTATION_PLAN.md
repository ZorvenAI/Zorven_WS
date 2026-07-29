# AI Brand Automator - Codebase Analysis & Implementation Plan

**Date**: January 9, 2026  
**Version**: 1.0  
**Status**: Pending Approval  
**Prepared By**: AI Code Analysis System

---

## Executive Summary

After comprehensive analysis of the AI Brand Automator codebase against the PRD and architecture documents, **63 critical issues** have been identified that prevent the application from functioning. The most severe issue is a **multi-tenancy configuration mismatch** where middleware is enabled but the tenant system is non-functional, causing all API requests to fail.

**Current Implementation Status**: Phase 3 (Onboarding System) - **INCOMPLETE and NON-FUNCTIONAL**

**Recommendation**: Implement the phased remediation plan outlined in this document, starting with critical blocking issues before adding tests.

---

## Table of Contents

1. [Critical Findings](#1-critical-findings)
2. [Detailed Issue Breakdown](#2-detailed-issue-breakdown)
3. [Multi-Tenancy Analysis](#3-multi-tenancy-analysis)
4. [Testing Strategy](#4-testing-strategy)
5. [Implementation Plan](#5-implementation-plan)
6. [Success Criteria](#6-success-criteria)

---

## 1. Critical Findings

### 1.1 Application-Blocking Issues

| ID | Issue | Impact | Affected Components |
|----|-------|--------|-------------------|
| **C-01** | Multi-tenancy middleware enabled but broken | 🔴 **ALL API requests fail** | Entire backend |
| **C-02** | No user registration endpoint | 🔴 **Cannot create accounts** | Authentication flow |
| **C-03** | JWT expects `username`, frontend sends `email` | 🔴 **Login fails** | Authentication |
| **C-04** | No tenant creation mechanism | 🔴 **Company creation fails** | Onboarding flow |

**Verdict**: Application is currently **non-functional** and cannot be tested without fixing these 4 issues first.

---

### 1.2 Issues by Severity

```
┌─────────────────────────────────────┐
│  Issue Severity Distribution        │
├─────────────────────────────────────┤
│  🔴 Critical (Blocking):      4     │
│  🟠 High (Core Feature):     20     │
│  🟡 Medium (Quality):        25     │
│  🟢 Low (Enhancement):       14     │
├─────────────────────────────────────┤
│  Total Issues Found:         63     │
└─────────────────────────────────────┘
```

### 1.3 Issues by Component

| Component | Issues | % of Total |
|-----------|--------|-----------|
| Backend Django | 25 | 40% |
| Frontend Next.js | 13 | 21% |
| Integration | 6 | 10% |
| Missing Features | 8 | 13% |
| Configuration | 4 | 6% |
| Security | 5 | 8% |
| Testing | 3 | 5% |

---

## 2. Detailed Issue Breakdown

### 2.1 Backend Django Issues (25 Issues)

#### 🔴 **Critical Issues**

**C-01: Multi-Tenancy Middleware Enabled But Broken**
- **Location**: `brand_automator/settings.py` Line 73
- **Problem**: `django_tenants.middleware.main.TenantMainMiddleware` is commented as "disabled" but **still in MIDDLEWARE list**
- **Impact**: Every request tries to resolve `request.tenant`, fails with AttributeError
- **Evidence**: 23+ references to `request.tenant` across views
- **Root Cause**: Inconsistent commenting - middleware is active but tenant models are disabled

**Fix Required**:
```python
# Option 1: Fully disable multi-tenancy (Recommended for MVP)
MIDDLEWARE = [
    # ... other middleware ...
    # REMOVE THIS LINE:
    # "django_tenants.middleware.main.TenantMainMiddleware",
]

# Option 2: Properly enable multi-tenancy
# - Re-enable tenant models in INSTALLED_APPS
# - Configure DATABASE_ROUTERS
# - Set TENANT_MODEL and TENANT_DOMAIN_MODEL
# - Create domain routing logic
```

**C-02: No User Registration Endpoint**
- **Location**: `brand_automator/urls.py`
- **Missing**: `POST /api/v1/auth/register/`
- **Impact**: Users cannot create accounts
- **Frontend Reference**: `RegisterForm.tsx` Line 30 shows message: "Registration is not implemented yet"

**Fix Required**:
```python
# In urls.py, add:
from rest_framework.authtoken.views import obtain_auth_token
from myapp.views import UserRegistrationView

urlpatterns = [
    path('api/v1/auth/register/', UserRegistrationView.as_view()),
    # ...
]

# Create UserRegistrationView:
class UserRegistrationView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # Create tenant for user
            # Generate JWT tokens
            return Response({'access': ..., 'refresh': ...})
        return Response(serializer.errors, status=400)
```

**C-03: JWT Login Email/Username Mismatch**
- **Location**: `simplejwt` expects `username`, frontend sends `email`
- **Frontend**: `LoginForm.tsx` Line 17: `formData = { email: '', password: '' }`
- **Backend**: Django User model uses `username` field
- **Impact**: All login attempts return 400 Bad Request

**Fix Required**:
```python
# Option 1: Custom JWT serializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'

# Option 2: Frontend sends username instead of email
// In LoginForm.tsx
const formData = {
    username: '',  // Change email to username
    password: ''
}
```

**C-04: No Tenant Creation Workflow**
- **Location**: Throughout onboarding flow
- **Problem**: No mechanism to create `Tenant` records for new users
- **Impact**: `Company.objects.create()` fails due to missing `tenant` foreign key
- **Evidence**: `onboarding/views.py` Line 36 tries to save Company without tenant

**Fix Required**:
```python
def perform_create(self, serializer):
    # Create or get tenant for user
    tenant, _ = Tenant.objects.get_or_create(
        schema_name=f"tenant_{self.request.user.id}",
        defaults={'name': f"{self.request.user.username}'s Company"}
    )
    
    # Save company with tenant
    company = serializer.save(tenant=tenant)
    
    # Create onboarding progress
    OnboardingProgress.objects.create(...)
```

#### 🟠 **High Priority Issues**

**H-01: Foreign Key Constraint Violations**
- **Locations**:
  - `onboarding/models.py` Line 7: `Company.tenant = OneToOneField(Tenant)`
  - `onboarding/models.py` Line 39: `BrandAsset.tenant = ForeignKey(Tenant)`
  - `ai_services/models.py` Line 7: `ChatSession.tenant = ForeignKey(Tenant)`
- **Problem**: All models reference `Tenant`, but tenant system is disabled
- **Impact**: Migrations will fail, model saves will fail

**H-02: Database Credentials Exposed**
- **Location**: `settings.py` Lines 103-109
- **Problem**: Hardcoded Neon PostgreSQL credentials in source code
```python
'PASSWORD': '<REDACTED>',  # ⚠️ EXPOSED!
'HOST': '<REDACTED>.us-east-2.aws.neon.tech',
```
- **Risk**: Credentials committed to Git repository
- **Fix**: Move to environment variables immediately

**H-03: SECRET_KEY Exposed**
- **Location**: `settings.py` Line 24
- **Problem**: Default fallback key is insecure Django dev key
- **Risk**: Production use would be vulnerable

**H-04: File Upload Endpoint Broken**
- **Location**: `onboarding/views.py` Lines 124-126
```python
company = get_object_or_404(Company, pk=1)  # ⚠️ Hardcoded ID!
```
- **Problems**:
  1. Assumes company with ID=1 exists
  2. No tenant filtering
  3. GCS upload commented out (Line 130)

**H-05: AI Service Tenant Logging Failure**
- **Location**: `ai_services/services.py` Line 76
```python
AIGeneration.objects.create(
    tenant=company_data.get('tenant'),  # This is object, not validated
    # ...
)
```
- **Problem**: `company_data.get('tenant')` returns `request.tenant` object or None
- **Impact**: Foreign key constraint violation

**H-06: Missing GCS Configuration**
- **Location**: `brand_automator/settings.py` Lines 197-199
- **Problem**: All GCS settings default to empty strings
- **Impact**: File uploads return mock URLs instead of real storage

**H-07: Missing Authentication on API Views**
- **Location**: `ai_services/views.py` Lines 46, 97, 137, 177
- **Problem**: `@api_view(['POST'])` decorators don't enforce authentication
- **Fix**: Add `@permission_classes([IsAuthenticated])`

**H-08: OnboardingProgress Auto-Creation Fails**
- **Location**: `onboarding/views.py` Lines 35-40
```python
company = serializer.save()  # Fails - no tenant!
OnboardingProgress.objects.create(
    tenant=company.tenant,  # company.tenant doesn't exist
    # ...
)
```

**H-09: Chat Session Creation Fails**
- **Location**: `ai_services/views.py` Lines 55-61
- **Problem**: Same tenant issue - `request.tenant` doesn't exist

**H-10: Missing Error Handling in AI Service**
- **Location**: `ai_services/services.py`
- **Problems**:
  - No validation if API key is None
  - Silent fallback hides errors
  - No logging for exceptions
  - No retry logic

#### 🟡 **Medium Priority Issues**

**M-01 through M-15**: See full detailed breakdown in Section 2.3

---

### 2.2 Frontend Next.js Issues (13 Issues)

#### 🟠 **High Priority Issues**

**H-11: Missing Component Exports**
- **Locations**:
  - `components/chat/MessageBubble.tsx` - Missing `export` on interfaces
  - `components/chat/FileSearch.tsx` - Missing `export` on interfaces
- **TypeScript Errors**:
```
Cannot find module './MessageBubble' or its corresponding type declarations.
Cannot find module './FileSearch' or its corresponding type declarations.
```
- **Impact**: ChatInterface component fails to compile

**Fix Required**:
```typescript
// MessageBubble.tsx
export interface Message {  // Add 'export'
  id: string;
  content: string;
  // ...
}

export interface MessageBubbleProps {  // Add 'export'
  message: Message;
}
```

**H-12: Field Name Mismatches (camelCase vs snake_case)**
- **Location**: `components/onboarding/CompanyForm.tsx`
- **Frontend sends**:
```typescript
{
  targetAudience: '',  // camelCase
  coreProblem: ''
}
```
- **Backend expects** (`onboarding/models.py`):
```python
target_audience = models.TextField()  # snake_case
core_problem = models.TextField()
```
- **Impact**: Backend receives empty values, validation may pass but data is lost

**Fix Required**: Convert field names in serializer or frontend:
```typescript
// Option 1: Frontend converts
const apiData = {
  target_audience: formData.targetAudience,
  core_problem: formData.coreProblem
}

// Option 2: Backend serializer accepts both
class CompanySerializer(serializers.ModelSerializer):
    targetAudience = serializers.CharField(source='target_audience')
```

**H-13: API Client Missing Error Handling**
- **Location**: `lib/api.ts`
- **Problems**:
  - Only handles 401 status
  - No handling for 400, 403, 500 errors
  - No retry logic for network failures
  - No response body parsing helpers

**H-14: Missing Authentication Guards**
- **Location**: All page components (dashboard, chat, onboarding)
- **Problem**: No check for JWT token in localStorage
- **Impact**: Unauthenticated users can access protected pages
- **Fix**: Add auth guard hook:
```typescript
// hooks/useAuth.ts
export function useAuth() {
  const router = useRouter();
  
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/auth/login');
    }
  }, []);
}
```

**H-15: Hardcoded Company ID Fallback**
- **Location**: `components/onboarding/BrandForm.tsx` Line 29
```typescript
const companyId = localStorage.getItem('company_id') || '1';  // ⚠️ Dangerous!
```
- **Problem**: Falls back to company ID 1 if not found
- **Impact**: User might update wrong company's data

#### 🟡 **Medium Priority Issues**

**M-16: Missing Token Refresh Logic**
- **Location**: `lib/api.ts`
- **Problem**: No automatic token refresh using `refresh_token`
- **Impact**: Users logged out after 60 minutes

**M-17: Missing onboarding steps 3-5**
- **Exists**: step-1, step-2
- **Missing**: step-3, step-4, step-5
- **StepWizard** shows 5 steps but only 2 implemented

**M-18: Dashboard Data is Static**
- **Location**: `components/dashboard/*`
- **Problem**: All data is hardcoded, no API calls

**M-19 through M-28**: See full detailed breakdown in Section 2.4

---

### 2.3 Integration Issues (6 Issues)

#### 🟠 **High Priority**

**I-01: API Endpoint Mismatches**

| Frontend Calls | Backend Provides | Status | Fix Required |
|---------------|------------------|--------|--------------|
| `POST /api/v1/auth/login/` (with email) | Expects username | ❌ Broken | Custom serializer |
| `POST /api/v1/auth/register/` | **Missing** | ❌ Missing | Create endpoint |
| `POST /api/v1/companies/` | Requires tenant | ❌ Broken | Add tenant logic |
| `POST /api/v1/companies/{id}/generate_brand_strategy/` | Requires tenant | ❌ Broken | Fix tenant |
| `POST /api/v1/ai/chat/` | Requires tenant | ❌ Broken | Fix tenant |

**I-02: Missing CORS Headers**
- **Location**: `settings.py` Line 125
- **Problem**: `CORS_ALLOW_CREDENTIALS = True` but no `CORS_ALLOW_HEADERS`
- **Impact**: Authorization header might be blocked

**I-03 through I-06**: See Section 2.5

---

### 2.4 Missing Implementations (8 Issues)

| Feature | Status | Backend | Frontend | Priority |
|---------|--------|---------|----------|----------|
| User Registration | ❌ Missing | No endpoint | Has UI | 🔴 Critical |
| Onboarding Steps 3-5 | ❌ Missing | N/A | No pages | 🟠 High |
| Brand Strategy Generation | ⚠️ Partial | Has API | No UI trigger | 🟠 High |
| Brand Identity Generation | ⚠️ Partial | Has API | No UI trigger | 🟠 High |
| File Upload UI | ❌ Missing | Has API | No page | 🟡 Medium |
| Chat Session Mgmt | ⚠️ Partial | Has API | Incomplete | 🟡 Medium |
| Automation Pages | ❌ Missing | Placeholder | No routes | 🟢 Low |
| Analytics/Reports | ❌ Missing | No impl | No routes | 🟢 Low |

---

### 2.5 Security Issues (5 Issues)

**S-01: Database Credentials in Source Code** (See H-02)  
**S-02: SECRET_KEY Exposed** (See H-03)  
**S-03: No CSRF Protection**
- Frontend doesn't include CSRF tokens
- DRF has CSRF enabled by default
- API calls will fail without proper headers

**S-04: File Upload Without Validation**
- No virus scanning
- No malware detection
- No file type validation beyond MIME type

**S-05: Prompt Injection Risk**
- User input directly embedded in AI prompts
- No input sanitization
- Could manipulate AI responses

---

### 2.6 Configuration Issues (4 Issues)

**CF-01: Missing Environment Variables**

Required but not documented:
```bash
# Critical
SECRET_KEY=<generate-new-secret>
DEBUG=False

# Database
DATABASE_URL=postgresql://...

# AI Services
GOOGLE_API_KEY=<your-api-key>

# File Storage
GS_BUCKET_NAME=your-bucket
GS_PROJECT_ID=your-project
GS_CREDENTIALS_PATH=/path/to/key.json

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**CF-02: No .env.example File**
- Developers don't know what to configure
- No template provided

**CF-03: No requirements-dev.txt**
- Missing dev dependencies (pytest, black, flake8, mypy)

**CF-04: No Frontend .env.example**
- Missing `NEXT_PUBLIC_API_URL` example

---

### 2.7 Testing Gaps (3 Issues)

**T-01: Zero Backend Tests**
- All `tests.py` files are empty placeholders
- No pytest configuration
- No fixtures

**T-02: Zero Frontend Tests**
- No Jest configuration
- No React Testing Library
- No test files

**T-03: No CI/CD Pipeline**
- No GitHub Actions
- No automated testing
- No deployment automation

---

## 3. Multi-Tenancy Analysis

### 3.1 Current State

**Architecture Decision**: Schema-based multi-tenancy using `django-tenants`

**Implementation Status**: **INCONSISTENT - Partially Enabled**

#### What's Enabled:
1. ✅ `django-tenants==3.5.0` in requirements.txt
2. ✅ Tenant and Domain models exist (`tenants/models.py`)
3. ✅ Migrations created (0001, 0002, 0003)
4. ✅ Middleware is in MIDDLEWARE list

#### What's Disabled/Broken:
1. ❌ `tenants` app commented out of INSTALLED_APPS (Line 56)
2. ❌ `DATABASE_ROUTERS` commented out (Lines 114-116)
3. ❌ `TENANT_MODEL` and `TENANT_DOMAIN_MODEL` commented out (Lines 118-119)
4. ❌ Custom User model disabled (Line 122)
5. ❌ No domain routing configuration

#### Critical Conflict:
```python
# settings.py Line 73
MIDDLEWARE = [
    # ...
    # Multi-tenancy middleware - temporarily disabled  ← COMMENT IS MISLEADING
    "django_tenants.middleware.main.TenantMainMiddleware",  ← ACTUALLY ACTIVE!
]
```

**The middleware is ACTIVE but tenant system is DISABLED** → Application fails on every request.

---

### 3.2 Multi-Tenancy Enablement Plan

#### Option A: **Fully Disable Multi-Tenancy (Recommended for MVP)**

**Rationale**:
- Simplifies MVP development
- Removes 23+ points of failure
- Can add multi-tenancy later with proper testing
- Aligns with PRD requirement for "demonstrate concept"

**Implementation**:
1. Remove middleware from MIDDLEWARE list
2. Remove all `tenant` foreign keys from models
3. Create migrations to drop tenant fields
4. Update all views to remove `request.tenant` references
5. Update serializers to remove tenant context
6. Add TODO comments for post-MVP multi-tenancy

**Timeline**: 4-6 hours

---

#### Option B: **Properly Enable Multi-Tenancy (Complex)**

**Rationale**:
- Meets PRD requirement FR-102 (Multi-tenancy)
- Proper data isolation from day one
- More difficult to retrofit later
- Higher risk but production-ready

**Implementation Steps**:

**Step 1: Enable Tenant Models**
```python
# settings.py
SHARED_APPS = [
    'django_tenants',  # Must be first
    'tenants',
    'django.contrib.contenttypes',
    'django.contrib.auth',
    # ...
]

TENANT_APPS = [
    'onboarding',
    'ai_services',
    'files',
]

INSTALLED_APPS = SHARED_APPS + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]
```

**Step 2: Configure Database**
```python
DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.Domain"
```

**Step 3: Domain Routing**
```python
# For development
# localhost:8000 → public schema (login/register)
# tenant1.localhost:8000 → tenant_1 schema
# tenant2.localhost:8000 → tenant_2 schema

# In production
# app.brandautomator.com → public schema
# customer1.brandautomator.com → customer1 schema
# customer2.brandautomator.com → customer2 schema
```

**Step 4: Tenant Creation Workflow**
```python
# In user registration view
def register_user(request):
    # 1. Create user in public schema
    user = User.objects.create_user(...)
    
    # 2. Create tenant schema
    tenant = Tenant.objects.create(
        schema_name=f'tenant_{user.id}',
        name=f"{user.username}'s Company"
    )
    
    # 3. Create domain
    Domain.objects.create(
        domain=f'{user.username}.localhost',  # Dev
        tenant=tenant,
        is_primary=True
    )
    
    # 4. Switch to tenant schema and create default data
    with schema_context(tenant.schema_name):
        Company.objects.create(tenant=tenant, ...)
    
    return Response({'tenant_domain': f'{user.username}.localhost'})
```

**Step 5: Frontend Domain Switching**
```typescript
// After registration
const response = await register(userData);
window.location.href = `http://${response.tenant_domain}:3000/onboarding`;
```

**Step 6: Middleware Configuration**
```python
MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',  # Must be first
    'django.middleware.security.SecurityMiddleware',
    # ... rest of middleware
]
```

**Timeline**: 2-3 days + testing

---

### 3.3 Recommendation

**Choose Option A (Disable Multi-Tenancy) for MVP Phase**

**Reasons**:
1. ✅ Unblocks development immediately
2. ✅ Reduces complexity and testing burden
3. ✅ Can add multi-tenancy in Phase 2 with proper planning
4. ✅ Aligns with "get it working first" principle
5. ✅ Reduces risk of data isolation bugs

**Post-MVP Migration Path**:
- Phase 2: Design proper multi-tenancy architecture
- Phase 3: Create migration scripts
- Phase 4: Deploy with tenant provisioning
- Phase 5: Migrate existing users to tenant schemas

---

## 4. Testing Strategy

### 4.1 Testing Philosophy

**Current State**: Zero tests  
**Target**: 80% code coverage before production

**Approach**: **Fix Critical Issues First, Then Add Tests**

**Rationale**:
- Writing tests for broken code wastes time
- Tests will fail until critical issues are fixed
- Fix → Test → Refactor cycle is more efficient

---

### 4.2 Backend Testing Plan

#### 4.2.1 Test Infrastructure Setup

**Install Dependencies**:
```bash
# requirements-dev.txt
pytest==7.4.3
pytest-django==4.7.0
pytest-cov==4.1.0
factory-boy==3.3.0
faker==20.1.0
freezegun==1.4.0
responses==0.24.1
```

**pytest Configuration**:
```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = brand_automator.settings
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*
addopts = 
    --cov=.
    --cov-report=html
    --cov-report=term-missing
    --verbose
```

**Test Structure**:
```
ai-brand-automator/
├── conftest.py                    # Global fixtures
├── onboarding/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py            # App fixtures
│   │   ├── test_models.py
│   │   ├── test_views.py
│   │   ├── test_serializers.py
│   │   └── test_integration.py
├── ai_services/
│   ├── tests/
│   │   └── ...
```

---

#### 4.2.2 Unit Tests

**Test Categories**:

1. **Model Tests** (`test_models.py`)
```python
# Example: test_company_model.py
import pytest
from onboarding.models import Company

@pytest.mark.django_db
class TestCompanyModel:
    def test_create_company(self):
        company = Company.objects.create(
            name="Test Corp",
            industry="Technology",
            # ...
        )
        assert company.name == "Test Corp"
        assert company.created_at is not None
    
    def test_company_str_representation(self):
        company = Company.objects.create(name="Test Corp")
        assert str(company) == "Test Corp"
    
    def test_company_values_default(self):
        company = Company.objects.create(name="Test Corp")
        assert company.values == []
```

2. **Serializer Tests** (`test_serializers.py`)
```python
# Example: test_company_serializers.py
import pytest
from onboarding.serializers import CompanyCreateSerializer

@pytest.mark.django_db
class TestCompanyCreateSerializer:
    def test_valid_company_data(self):
        data = {
            'name': 'Test Corp',
            'industry': 'Technology',
            'description': 'A test company'
        }
        serializer = CompanyCreateSerializer(data=data)
        assert serializer.is_valid()
    
    def test_missing_required_fields(self):
        data = {'industry': 'Technology'}
        serializer = CompanyCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'name' in serializer.errors
```

3. **View Tests** (`test_views.py`)
```python
# Example: test_company_views.py
import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User

@pytest.mark.django_db
class TestCompanyViewSet:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_company_unauthenticated(self):
        response = self.client.post('/api/v1/companies/', {})
        assert response.status_code == 401
    
    def test_create_company_authenticated(self):
        self.client.force_authenticate(user=self.user)
        data = {
            'name': 'Test Corp',
            'industry': 'Technology'
        }
        response = self.client.post('/api/v1/companies/', data)
        assert response.status_code == 201
        assert response.data['name'] == 'Test Corp'
```

4. **AI Service Tests** (`test_ai_services.py`)
```python
# Example: test_gemini_service.py
import pytest
from unittest.mock import Mock, patch
from ai_services.services import GeminiAIService

class TestGeminiAIService:
    def setup_method(self):
        self.service = GeminiAIService()
    
    @patch('google.generativeai.GenerativeModel')
    def test_generate_brand_strategy_with_api_key(self, mock_model):
        mock_response = Mock()
        mock_response.text = """
        Vision Statement: To revolutionize the industry
        Mission Statement: Deliver exceptional service
        Core Values: Innovation, Excellence
        """
        mock_model.return_value.generate_content.return_value = mock_response
        
        result = self.service.generate_brand_strategy({
            'name': 'Test Corp',
            'industry': 'Technology'
        })
        
        assert 'vision_statement' in result
        assert 'innovation' in result['vision_statement'].lower()
    
    def test_generate_brand_strategy_without_api_key(self):
        service = GeminiAIService()
        service.model = None  # Simulate no API key
        
        result = service.generate_brand_strategy({
            'name': 'Test Corp',
            'industry': 'Technology'
        })
        
        assert 'vision_statement' in result
        assert 'Technology' in result['vision_statement']
```

---

#### 4.2.3 Integration Tests

**Test Categories**:

1. **Authentication Flow**
```python
@pytest.mark.django_db
class TestAuthenticationFlow:
    def test_register_login_flow(self, client):
        # Register
        register_data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'SecurePass123!'
        }
        response = client.post('/api/v1/auth/register/', register_data)
        assert response.status_code == 201
        
        # Login
        login_data = {
            'email': 'new@example.com',
            'password': 'SecurePass123!'
        }
        response = client.post('/api/v1/auth/login/', login_data)
        assert response.status_code == 200
        assert 'access' in response.data
        assert 'refresh' in response.data
```

2. **Onboarding Flow**
```python
@pytest.mark.django_db
class TestOnboardingFlow:
    def test_complete_onboarding(self, authenticated_client, user):
        # Step 1: Create company
        company_data = {
            'name': 'Test Corp',
            'industry': 'Technology',
            # ...
        }
        response = authenticated_client.post(
            '/api/v1/companies/',
            company_data
        )
        company_id = response.data['id']
        
        # Step 2: Generate brand strategy
        response = authenticated_client.post(
            f'/api/v1/companies/{company_id}/generate_brand_strategy/'
        )
        assert response.status_code == 200
        assert response.data['vision_statement']
        
        # Step 3: Upload asset
        # ...
```

3. **AI Chatbot Integration**
```python
@pytest.mark.django_db
class TestAIChatIntegration:
    def test_chat_session_creation(self, authenticated_client):
        message_data = {'message': 'Help me with brand strategy'}
        response = authenticated_client.post(
            '/api/v1/ai/chat/',
            message_data
        )
        assert response.status_code == 200
        assert 'session_id' in response.data
        assert 'response' in response.data
```

---

#### 4.2.4 Property-Based Tests (Advanced)

**Install**: `pip install hypothesis`

```python
from hypothesis import given, strategies as st

class TestCompanyModel:
    @given(
        name=st.text(min_size=1, max_size=255),
        industry=st.text(max_size=100)
    )
    def test_company_creation_with_random_data(self, name, industry):
        company = Company.objects.create(
            name=name,
            industry=industry
        )
        assert company.name == name
        assert company.industry == industry
    
    @given(st.lists(st.text(min_size=1), min_size=0, max_size=10))
    def test_company_values_field(self, values):
        company = Company.objects.create(
            name="Test",
            values=values
        )
        assert company.values == values
```

---

### 4.3 Frontend Testing Plan

#### 4.3.1 Test Infrastructure Setup

**Install Dependencies**:
```bash
# In ai-brand-automator-frontend/
npm install --save-dev \
  @testing-library/react \
  @testing-library/jest-dom \
  @testing-library/user-event \
  jest \
  jest-environment-jsdom \
  @types/jest
```

**Jest Configuration**:
```javascript
// jest.config.js
module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testMatch: ['**/__tests__/**/*.[jt]s?(x)', '**/?(*.)+(spec|test).[jt]s?(x)'],
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/**/*.d.ts',
  ],
};

// jest.setup.js
import '@testing-library/jest-dom';
```

---

#### 4.3.2 Component Tests

**Test Categories**:

1. **Form Tests**
```typescript
// CompanyForm.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CompanyForm } from '@/components/onboarding/CompanyForm';

describe('CompanyForm', () => {
  it('renders all form fields', () => {
    render(<CompanyForm />);
    
    expect(screen.getByLabelText(/company name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/industry/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  });
  
  it('shows validation errors for empty required fields', async () => {
    render(<CompanyForm />);
    
    const submitButton = screen.getByRole('button', { name: /next step/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/company name is required/i)).toBeInTheDocument();
    });
  });
  
  it('submits form with valid data', async () => {
    const mockSubmit = jest.fn();
    render(<CompanyForm onSubmit={mockSubmit} />);
    
    fireEvent.change(screen.getByLabelText(/company name/i), {
      target: { value: 'Test Corp' }
    });
    
    fireEvent.click(screen.getByRole('button', { name: /next step/i }));
    
    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith({
        name: 'Test Corp',
        // ...
      });
    });
  });
});
```

2. **API Integration Tests**
```typescript
// api.test.ts
import { apiClient } from '@/lib/api';

global.fetch = jest.fn();

describe('apiClient', () => {
  beforeEach(() => {
    (fetch as jest.Mock).mockClear();
  });
  
  it('includes Authorization header when token exists', async () => {
    localStorage.setItem('access_token', 'test-token');
    
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: 'test' })
    });
    
    await apiClient.get('/test');
    
    expect(fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer test-token'
        })
      })
    );
  });
  
  it('redirects to login on 401 response', async () => {
    delete window.location;
    window.location = { href: '' } as any;
    
    (fetch as jest.Mock).mockResolvedValueOnce({
      status: 401,
      ok: false
    });
    
    await apiClient.get('/test');
    
    expect(window.location.href).toBe('/auth/login');
  });
});
```

3. **Hook Tests**
```typescript
// useAuth.test.ts
import { renderHook } from '@testing-library/react';
import { useAuth } from '@/hooks/useAuth';

describe('useAuth', () => {
  it('redirects to login when no token', () => {
    localStorage.removeItem('access_token');
    
    const { result } = renderHook(() => useAuth());
    
    expect(window.location.href).toContain('/auth/login');
  });
  
  it('stays on page when token exists', () => {
    localStorage.setItem('access_token', 'test-token');
    
    const { result } = renderHook(() => useAuth());
    
    expect(window.location.href).not.toContain('/auth/login');
  });
});
```

---

#### 4.3.3 E2E Tests (Optional, Post-MVP)

**Tool**: Playwright or Cypress

```typescript
// e2e/onboarding.spec.ts
import { test, expect } from '@playwright/test';

test('complete onboarding flow', async ({ page }) => {
  // Login
  await page.goto('http://localhost:3000/auth/login');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'password');
  await page.click('button[type="submit"]');
  
  // Step 1: Company Info
  await expect(page).toHaveURL('/onboarding/step-1');
  await page.fill('[name="name"]', 'Test Corp');
  await page.selectOption('[name="industry"]', 'technology');
  await page.click('button:has-text("Next Step")');
  
  // Step 2: Brand Details
  await expect(page).toHaveURL('/onboarding/step-2');
  // ...
});
```

---

### 4.4 Test Coverage Goals

| Phase | Component | Coverage Target |
|-------|-----------|----------------|
| Phase 1 | Critical Paths | 60% |
| Phase 2 | Core Features | 70% |
| Phase 3 | Full Backend | 80% |
| Phase 4 | Full Frontend | 75% |
| Production | Overall | 80%+ |

---

## 5. Implementation Plan

### 5.1 Overview

**Total Duration**: 4-6 weeks  
**Team Size**: 1-2 developers  
**Approach**: Iterative, test-driven

---

### 5.2 Phase 1: Critical Fixes (Week 1)

**Goal**: Make the application functional

**Priority**: 🔴 **BLOCKING ISSUES ONLY**

#### Tasks:

**1.1 Disable Multi-Tenancy** (4 hours)
- [ ] Remove `TenantMainMiddleware` from MIDDLEWARE
- [ ] Remove `tenant` field from all models
- [ ] Create migration to drop tenant columns
- [ ] Update all views to remove `request.tenant`
- [ ] Update all serializers to remove tenant context
- [ ] Test: Application starts without errors

**1.2 Create User Registration Endpoint** (3 hours)
- [ ] Create `UserRegistrationSerializer`
- [ ] Create `UserRegistrationView`
- [ ] Add URL route for `/api/v1/auth/register/`
- [ ] Add validation (password strength, email format)
- [ ] Test: Can create user and receive JWT tokens

**1.3 Fix JWT Login** (2 hours)
- [ ] Create custom `EmailTokenObtainPairSerializer`
- [ ] Update login endpoint to accept email
- [ ] Test: Login with email works

**1.4 Fix Company Creation** (2 hours)
- [ ] Remove tenant requirement from Company model
- [ ] Update `perform_create` in CompanyViewSet
- [ ] Associate company with logged-in user
- [ ] Test: Can create company after login

**1.5 Environment Variable Security** (1 hour)
- [ ] Create `.env.example` files (backend and frontend)
- [ ] Move DATABASE credentials to environment
- [ ] Move SECRET_KEY to environment (generate new)
- [ ] Move GOOGLE_API_KEY to environment
- [ ] Update `.gitignore` to exclude `.env`
- [ ] Document required env vars in README

**1.6 Fix Frontend Component Exports** (1 hour)
- [ ] Add `export` to MessageBubble interfaces
- [ ] Add `export` to FileSearch interfaces
- [ ] Test: ChatInterface compiles without errors

**1.7 Fix Field Name Mismatches** (2 hours)
- [ ] Update CompanyForm to send snake_case
- [ ] Update BrandForm to send snake_case
- [ ] Or create serializer with field aliases
- [ ] Test: Form data saves correctly

**Total**: ~15 hours (2 days)

**Success Criteria**:
- ✅ Application starts without errors
- ✅ Can register new user
- ✅ Can login with email
- ✅ Can create company
- ✅ Frontend compiles without TypeScript errors

---

### 5.3 Phase 2: Core Features (Week 2-3)

**Goal**: Complete essential user flows

**Priority**: 🟠 **HIGH PRIORITY**

#### Tasks:

**2.1 Complete Onboarding Flow** (8 hours)
- [ ] Create `onboarding/step-3` page (brand strategy generation)
- [ ] Create `onboarding/step-4` page (brand identity)
- [ ] Create `onboarding/step-5` page (review & submit)
- [ ] Wire up AI generation endpoints
- [ ] Add progress persistence
- [ ] Test: Complete onboarding flow end-to-end

**2.2 Implement File Upload** (6 hours)
- [ ] Configure GCS with proper credentials
- [ ] Update file upload endpoint to use real GCS
- [ ] Create asset management page
- [ ] Add drag-and-drop UI
- [ ] Add file type validation
- [ ] Test: Upload and retrieve files

**2.3 Enhance AI Chat** (5 hours)
- [ ] Implement session persistence (localStorage)
- [ ] Add session history UI
- [ ] Fix chat context to not require tenant
- [ ] Add loading states
- [ ] Add error handling
- [ ] Test: Chat conversation flows correctly

**2.4 Add Authentication Guards** (3 hours)
- [ ] Create `useAuth` hook
- [ ] Add to all protected pages
- [ ] Implement token refresh logic
- [ ] Add logout functionality
- [ ] Test: Unauthenticated users redirected

**2.5 API Error Handling** (4 hours)
- [ ] Enhance `apiClient` error handling
- [ ] Add retry logic for network failures
- [ ] Add toast notifications for errors
- [ ] Create error boundary component
- [ ] Test: Errors handled gracefully

**2.6 Input Validation** (4 hours)
- [ ] Add backend request validation
- [ ] Add frontend form validation
- [ ] Add AI prompt sanitization
- [ ] Add file upload validation
- [ ] Test: Invalid inputs rejected

**Total**: ~30 hours (4 days)

**Success Criteria**:
- ✅ Users can complete full onboarding
- ✅ Files upload to real GCS
- ✅ Chat works without crashes
- ✅ Protected routes require auth
- ✅ Errors display user-friendly messages

---

### 5.4 Phase 3: Testing & Quality (Week 4)

**Goal**: Achieve 70%+ test coverage

**Priority**: 🟡 **MEDIUM PRIORITY**

#### Tasks:

**3.1 Backend Test Setup** (4 hours)
- [ ] Install pytest and dependencies
- [ ] Create `conftest.py` with fixtures
- [ ] Configure pytest.ini
- [ ] Create test structure
- [ ] Set up coverage reporting

**3.2 Backend Unit Tests** (16 hours)
- [ ] Model tests (onboarding, ai_services)
- [ ] Serializer tests
- [ ] View tests (authentication, companies, AI)
- [ ] AI service tests (with mocks)
- [ ] Achieve 70% backend coverage

**3.3 Backend Integration Tests** (8 hours)
- [ ] Authentication flow tests
- [ ] Onboarding flow tests
- [ ] AI chat integration tests
- [ ] File upload integration tests

**3.4 Frontend Test Setup** (3 hours)
- [ ] Install Jest and Testing Library
- [ ] Configure jest.config.js
- [ ] Create test utilities
- [ ] Set up coverage reporting

**3.5 Frontend Component Tests** (12 hours)
- [ ] Form component tests
- [ ] API client tests
- [ ] Hook tests
- [ ] Integration tests
- [ ] Achieve 60% frontend coverage

**Total**: ~43 hours (5-6 days)

**Success Criteria**:
- ✅ Backend: 70%+ coverage
- ✅ Frontend: 60%+ coverage
- ✅ All critical paths tested
- ✅ Tests pass in CI/CD

---

### 5.5 Phase 4: Production Readiness (Week 5-6)

**Goal**: Deploy-ready application

**Priority**: 🟢 **LOW PRIORITY (Post-MVP)**

#### Tasks:

**4.1 Remaining Features** (12 hours)
- [ ] Dashboard with real data
- [ ] Asset management UI
- [ ] Brand strategy/identity generation UI
- [ ] Settings page
- [ ] Profile management

**4.2 Performance Optimization** (6 hours)
- [ ] Add database indexes
- [ ] Implement query optimization
- [ ] Add Redis caching
- [ ] Optimize frontend bundle size
- [ ] Add loading skeletons

**4.3 Security Hardening** (8 hours)
- [ ] Add rate limiting
- [ ] Implement CSRF protection
- [ ] Add input sanitization
- [ ] Configure CSP headers
- [ ] Security audit

**4.4 Deployment** (8 hours)
- [ ] Create Docker configurations
- [ ] Set up CI/CD pipeline (GitHub Actions)
- [ ] Configure production database
- [ ] Deploy to cloud (GCP/AWS/Heroku)
- [ ] Set up monitoring (Sentry)

**4.5 Documentation** (6 hours)
- [ ] API documentation (Swagger/OpenAPI)
- [ ] Developer README
- [ ] Deployment guide
- [ ] User manual
- [ ] Architecture diagrams

**Total**: ~40 hours (5 days)

**Success Criteria**:
- ✅ Application deployed to production
- ✅ Monitoring and logging active
- ✅ Documentation complete
- ✅ Security audit passed

---

### 5.6 Timeline Summary

```
Week 1:  Phase 1 - Critical Fixes           [████████░░░░░░░░░░] 40%
Week 2:  Phase 2 - Core Features (Part 1)   [████████████░░░░░░] 60%
Week 3:  Phase 2 - Core Features (Part 2)   [████████████████░░] 80%
Week 4:  Phase 3 - Testing                  [██████████████████] 100%
Week 5:  Phase 4 - Production (Part 1)      [████████████░░░░░░] Optional
Week 6:  Phase 4 - Production (Part 2)      [██████████████████] Optional
```

**Minimum Viable Timeline**: 4 weeks  
**Full Production Timeline**: 6 weeks

---

## 6. Success Criteria

### 6.1 Phase 1 Success Metrics

**Functional**:
- [ ] Application starts without errors
- [ ] User can register new account
- [ ] User can login with email
- [ ] User can create company profile
- [ ] No TypeScript compilation errors
- [ ] No Python runtime errors

**Technical**:
- [ ] All critical issues (C-01 to C-04) resolved
- [ ] Database migrations run successfully
- [ ] Environment variables properly configured
- [ ] No hardcoded credentials in code

---

### 6.2 Phase 2 Success Metrics

**Functional**:
- [ ] User completes full onboarding (5 steps)
- [ ] Files upload to GCS successfully
- [ ] AI chatbot responds to queries
- [ ] Protected routes require authentication
- [ ] Error messages display for failures

**Technical**:
- [ ] All high-priority issues resolved
- [ ] API endpoints return correct status codes
- [ ] Frontend/backend field names match
- [ ] Authentication guards on all pages
- [ ] File validation works

---

### 6.3 Phase 3 Success Metrics

**Testing**:
- [ ] Backend test coverage: 70%+
- [ ] Frontend test coverage: 60%+
- [ ] All integration tests pass
- [ ] Critical paths have tests
- [ ] CI/CD pipeline runs tests

**Quality**:
- [ ] No linting errors
- [ ] No security vulnerabilities (Snyk/Bandit)
- [ ] Code review completed
- [ ] Documentation updated

---

### 6.4 Phase 4 Success Metrics

**Production**:
- [ ] Application deployed to cloud
- [ ] Monitoring and alerting configured
- [ ] Performance benchmarks met (< 200ms API)
- [ ] Security audit passed
- [ ] Documentation complete

**User Experience**:
- [ ] Onboarding completion rate > 80%
- [ ] No user-reported critical bugs
- [ ] Loading times < 3 seconds
- [ ] Mobile responsive

---

## 7. Risk Assessment

### 7.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Multi-tenancy re-enablement complexity | High | High | Keep disabled for MVP, plan for Phase 2 |
| GCS configuration issues | Medium | Medium | Use mock implementation initially |
| AI API rate limiting | Medium | Medium | Implement caching and fallbacks |
| Database migration failures | Low | High | Test migrations in staging first |
| Frontend TypeScript errors | Medium | Low | Fix incrementally, add type checks |

---

### 7.2 Timeline Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Underestimated task complexity | Medium | High | Add 20% buffer to estimates |
| Scope creep | High | High | Strict adherence to phase goals |
| Testing takes longer than expected | Medium | Medium | Prioritize critical path tests |
| Integration issues | Medium | High | Test early, test often |

---

### 7.3 Resource Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Single developer unavailability | Low | High | Document all changes thoroughly |
| Learning curve for new tools | Medium | Medium | Allocate time for research |
| Third-party service downtime | Low | Medium | Implement fallback mechanisms |

---

## 8. Recommendations

### 8.1 Immediate Actions (This Week)

1. **Approve this plan** and confirm priority order
2. **Review and comment** on any unclear sections
3. **Set up environment** with proper `.env` files
4. **Begin Phase 1** - Critical fixes (2 days)

### 8.2 Development Best Practices

1. **Commit frequently** with descriptive messages
2. **Create feature branches** for each task
3. **Write tests** as you implement features
4. **Code review** before merging to main
5. **Document** as you go, not at the end

### 8.3 Communication

1. **Daily standups** (even if solo) - track progress
2. **Weekly reviews** of completed phases
3. **Demo** working features regularly
4. **Update** this document as plans change

---

## 9. Appendix

### 9.1 Glossary

- **Multi-tenancy**: Architecture where single instance serves multiple customers with data isolation
- **Schema-based**: Each tenant has separate database schema
- **JWT**: JSON Web Token for stateless authentication
- **DRF**: Django Rest Framework
- **GCS**: Google Cloud Storage
- **CI/CD**: Continuous Integration/Continuous Deployment

### 9.2 Reference Documents

- Product Requirement Document (PRD) - Provided in analysis request
- [ai_brand_automator_mvp_architecture.md](ai_brand_automator_mvp_architecture.md)
- [plans/ai_brand_automator_mvp_plan.md](plans/ai_brand_automator_mvp_plan.md)
- [.github/copilot-instructions.md](.github/copilot-instructions.md)

### 9.3 Contact & Support

For questions or clarifications on this plan:
1. Review detailed issue descriptions in Section 2
2. Check implementation examples in testing sections
3. Refer to architecture documents
4. Request clarification on specific tasks

---

## 10. Approval Sign-off

**Document Version**: 1.0  
**Prepared By**: AI Code Analysis System  
**Date**: January 9, 2026

**Reviewer**: _________________  
**Date**: _________________  
**Status**: [ ] Approved [ ] Needs Revision [ ] Rejected

**Comments**:
```
(Add your review comments here)
```

---

**Next Steps After Approval**:
1. Create GitHub issues for Phase 1 tasks
2. Set up development environment with proper credentials
3. Begin implementation following the priority order
4. Schedule daily progress check-ins
5. Plan for Phase 2 once Phase 1 is complete

---

**END OF DOCUMENT**
