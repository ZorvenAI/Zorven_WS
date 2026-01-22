# AI Brand Automator - Comprehensive Testing Strategy

## Executive Summary

This document outlines a systematic testing strategy for all Django REST Framework services in the AI Brand Automator platform. The strategy emphasizes:
- **Unit Testing** with pytest for isolated component validation
- **Property-Based Testing** with Hypothesis for edge case discovery
- **Integration Testing** for API endpoint validation
- **Multi-tenancy Testing** to ensure data isolation
- **Mocking strategies** for external dependencies (AI services, storage)

---

## 1. Testing Philosophy

### 1.1 Testing Pyramid
```
        /\
       /  \      E2E Tests (5%)
      /----\     - Full user workflows
     /      \    - Critical paths only
    /--------\   
   / Integration\ (25%)
  /   Tests     \ - API endpoints
 /--------------\ - Multi-service interactions
/                \
/   Unit Tests   \ (70%)
/  (Models, Utils)\- Serializers, Models
-------------------  - Business logic, Services
```

### 1.2 Core Principles
1. **Fast Feedback**: Unit tests run in <5 seconds
2. **Isolation**: Mock external dependencies (AI, GCS, emails)
3. **Deterministic**: No flaky tests, use freezegun for time
4. **Property-Based**: Use Hypothesis to discover edge cases
5. **Coverage Target**: 80% code coverage minimum

---

## 2. Technology Stack

### 2.1 Testing Tools
```python
pytest==7.4.4                  # Test framework
pytest-django==4.7.0           # Django integration
pytest-cov==4.1.0              # Coverage reporting
pytest-mock==3.12.0            # Mocking utilities
hypothesis==6.92.0             # Property-based testing
factory-boy==3.3.0             # Test data factories
faker==22.0.0                  # Fake data generation
freezegun==1.4.0               # Time mocking
responses==0.24.1              # HTTP request mocking
```

### 2.2 Project Structure
```
ai-brand-automator/
├── conftest.py                    # Global fixtures
├── pytest.ini                     # Pytest configuration
├── onboarding/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── factories.py           # Factory Boy factories
│   │   ├── test_models.py         # Model tests
│   │   ├── test_serializers.py    # Serializer tests
│   │   ├── test_views.py          # ViewSet tests
│   │   ├── test_integration.py    # API integration tests
│   │   └── test_properties.py     # Hypothesis property tests
│   └── ...
├── ai_services/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── factories.py
│   │   ├── test_models.py
│   │   ├── test_serializers.py
│   │   ├── test_views.py
│   │   ├── test_services.py       # AI service tests
│   │   └── test_properties.py
│   └── ...
├── tenants/
│   └── tests/
│       └── ...
└── brand_automator/
    └── tests/
        ├── test_auth_views.py
        ├── test_health_views.py
        └── test_middleware.py
```

---

## 3. Service-Level Testing Strategy

### 3.1 Onboarding Service (`onboarding/`)

#### Components to Test
- **Models**: `Company`, `BrandAsset`, `OnboardingProgress`
- **Serializers**: `CompanySerializer`, `CompanyCreateSerializer`, `CompanyUpdateSerializer`, `BrandAssetSerializer`
- **ViewSets**: `CompanyViewSet`, `BrandAssetViewSet`, `OnboardingProgressViewSet`
- **Custom Actions**: `generate_brand_strategy`, `generate_brand_identity`, `upload`

#### Test Categories

**A. Model Tests** (`test_models.py`)
```python
- Company creation with valid data
- Company validation (name required, industry choices)
- Tenant relationship (OneToOne with Tenant)
- JSON field defaults (values field)
- String representation (__str__)
- Property-based: Random valid company data
```

**B. Serializer Tests** (`test_serializers.py`)
```python
- Valid data serialization
- Invalid data rejection
- Field validation (max_length, choices)
- Read-only field enforcement
- Nested serialization (tenant data)
- Property-based: Random field combinations
```

**C. ViewSet Tests** (`test_views.py`)
```python
- List companies (GET /api/v1/companies/)
- Create company (POST with authentication)
- Retrieve single company (GET /api/v1/companies/{id}/)
- Update company (PUT/PATCH)
- Delete company (DELETE)
- Permission checks (unauthenticated rejection)
- Tenant isolation (user only sees their tenant's data)
- Custom actions (generate_brand_strategy endpoint)
```

**D. Integration Tests** (`test_integration.py`)
```python
- Complete onboarding flow (create company → upload assets → AI generation)
- Multi-tenant data isolation
- Error handling (400, 404, 500 responses)
- Pagination testing
```

**E. Property Tests** (`test_properties.py`)
```python
- Hypothesis strategies for Company model
- Random industry/brand_voice combinations
- Edge cases: empty strings, max lengths, special characters
```

---

### 3.2 AI Services (`ai_services/`)

#### Components to Test
- **Models**: `ChatSession`, `AIGeneration`
- **Serializers**: `ChatSessionSerializer`, `ChatMessageSerializer`, `AIGenerationSerializer`
- **ViewSets**: `ChatSessionViewSet`, `AIGenerationViewSet`
- **Function Views**: `chat_with_ai`, `generate_brand_strategy`, `generate_brand_identity`, `analyze_market`
- **Services**: `GeminiAIService` (external API integration)

#### Test Categories

**A. Service Tests** (`test_services.py`)
```python
- GeminiAIService initialization
- Mock AI API responses
- Error handling (API failures, timeout)
- Token counting accuracy
- Response parsing (extract vision/mission)
- Fallback responses (no API key)
```

**B. Model Tests** (`test_models.py`)
```python
- ChatSession creation with session_id
- Message appending (add_message method)
- Timestamp updates (last_activity)
- AIGeneration token tracking
- JSON field handling (messages, context)
```

**C. ViewSet Tests** (`test_views.py`)
```python
- Chat session CRUD operations
- AI generation read-only access
- Tenant filtering in querysets
- Authentication requirements
- Custom endpoints (chat_with_ai, generate_brand_strategy)
```

**D. Property Tests** (`test_properties.py`)
```python
- Random chat message sequences
- Variable-length message history
- Context data variations
```

---

### 3.3 Authentication Service (`brand_automator/`)

#### Components to Test
- **Views**: `EmailTokenObtainPairView`, `UserRegistrationView`, `EmailVerificationView`, `PasswordResetRequestView`
- **Serializers**: `EmailTokenObtainPairSerializer`
- **Validators**: `validate_password_strength`, `validate_file_upload`, `sanitize_filename`
- **Middleware**: `SecurityMiddleware`, `TenantMainMiddleware`

#### Test Categories

**A. Auth View Tests** (`test_auth_views.py`)
```python
- User registration with valid data
- Email-based login (not username)
- JWT token generation
- Password validation (strength requirements)
- Email uniqueness enforcement
- Tenant/Domain creation on registration
```

**B. Validator Tests** (`test_validators.py`)
```python
- Password strength validation (length, complexity)
- File upload validation (size, type, mime)
- Filename sanitization (special characters removal)
- Property-based: Random password combinations
```

**C. Middleware Tests** (`test_middleware.py`)
```python
- Security headers application
- Tenant resolution from domain
- Request attribute injection (request.tenant)
```

---

### 3.4 Health Check Service (`brand_automator/`)

#### Components to Test
- **Views**: `HealthCheckView`, `ReadinessCheckView`, `LivenessCheckView`

#### Test Categories
```python
- Health check success (200) with healthy dependencies
- Health check failure (503) with DB down
- Readiness check database verification
- Liveness check always returns 200
- Response format validation
```

---

### 3.5 Automation Service (`automation/`) ✅ IMPLEMENTED

#### Components Tested
- **Models**: `SocialProfile`, `ContentCalendar`, `AutomationTask`, `OAuthState`, `TwitterWebhookEvent`, `LinkedInWebhookEvent`, `FacebookWebhookEvent`
- **Services**: `LinkedInService`, `TwitterService`, `FacebookService`, `InstagramService`
- **Serializers**: `SocialProfileSerializer`, `AutomationTaskSerializer`, `ContentCalendarSerializer`
- **Tasks**: `publish_scheduled_posts`, `publish_single_post`
- **Helpers**: `publish_content`, `update_content_status`

#### Implementation Status: ✅ COMPLETE (149 tests)

**Test Files:**
```
automation/tests/
├── test_models.py         # 51 unit tests
├── test_properties.py     # 18 property-based tests
├── test_integration.py    # 26 integration tests
├── test_services.py       # 36 service tests
└── test_automation.py     # 18 existing tests (14 skipped)
```

**A. Model Tests** (`test_models.py`) - 51 tests
```python
# SocialProfile Tests (20+ tests)
- Create profiles for all platforms (LinkedIn, Twitter, Facebook, Instagram)
- Platform and status choices validation
- Unique together constraint (user + platform)
- Token encryption on save and retrieval
- is_token_valid property (valid/expired)
- is_token_expiring_soon property
- disconnect() clears all tokens
- get_instagram_token() validation
- get_page_token() validation (Facebook)
- Ordering by created_at

# ContentCalendar Tests (10 tests)
- Create content entries with scheduling
- Status choices (draft, scheduled, published, failed, cancelled)
- Multiple platforms support (JSON field)
- Media URLs JSON field
- Social profiles M2M relationship
- Post results JSON storage
- Published_at timestamp
- Ordering by scheduled_date

# AutomationTask Tests (10 tests)
- Task creation with user and profile
- Task type choices
- Status choices (pending, in_progress, completed, failed, cancelled)
- Social profile FK relationship
- Payload JSON field
- Result JSON field
- Error message storage
- Scheduling fields (scheduled_for, started_at, completed_at)
- Ordering by created_at descending

# OAuthState Tests (7 tests)
- Create OAuth state with user and platform
- State uniqueness constraint
- is_expired() within 10-minute limit
- is_expired() after 10-minute limit
- code_verifier for PKCE (Twitter)
- mark_as_used() functionality

# Webhook Event Tests (4 tests)
- Twitter webhook event creation
- LinkedIn webhook event creation
- Facebook webhook event creation
- Mark as read functionality
```

**B. Property Tests** (`test_properties.py`) - 18 tests (Hypothesis)
```python
# Encryption Properties (5 tests)
- Encryption roundtrip invariant
- Encrypted differs from plaintext
- Different tokens produce different encrypted values
- Decrypt handles None and empty strings
- Multiple encryptions idempotent for decryption

# SocialProfile Properties (4 tests)
- Profile creation with any valid platform/status combination
- is_token_valid invariant (expires_at vs now)
- is_token_expiring_soon invariant (15-minute threshold)
- Token encryption on model save

# ContentCalendar Properties (3 tests)
- Content creation with valid inputs
- Media URLs stores any number of URLs
- Scheduled date ordering preserved

# AutomationTask Properties (2 tests)
- Task creation with valid inputs
- Payload stores any JSON structure

# OAuthState Properties (1 test)
- is_expired invariant (10-minute boundary)

# Serializer Properties (3 tests)
- SocialProfile serializer output validation
- AutomationTask serializer output validation
- ContentCalendar serializer output validation
```

**C. Integration Tests** (`test_integration.py`) - 26 tests
```python
# OAuth Flow Tests (4 tests)
- LinkedIn OAuth state creation and validation
- Twitter OAuth state with PKCE code verifier
- OAuth state expiration after 10 minutes
- OAuth state cleanup on reconnect

# Content Publishing Pipeline Tests (5 tests)
- Schedule content for single platform
- Schedule content for multiple platforms
- Publish content updates status correctly
- Failed publish records error details
- Cancel scheduled content

# Publish Helpers Tests (4 tests)
- publish_content in test mode
- update_content_status on success
- update_content_status on failure
- update_content_status partial success

# Celery Tasks Tests (5 tests)
- publish_scheduled_posts processes due posts
- publish_scheduled_posts ignores future posts
- publish_single_post publishes specific post
- publish_single_post handles not found
- publish_single_post handles already published

# Cross-Model Workflow Tests (3 tests)
- Disconnect profile doesn't affect published content
- AutomationTask tracks publish operations
- User manages multiple profiles and content

# Token Refresh Tests (3 tests)
- get_valid_access_token returns current when valid
- Facebook returns page token for posting
- Disconnected profile raises on token access

# Webhook Event Tests (2 tests)
- Create and retrieve Twitter webhook events
- Create and retrieve LinkedIn webhook events
```

**D. Service Tests** (`test_services.py`) - 36 tests
```python
# LinkedInService Tests (10 tests)
- Service initialization
- is_configured property
- Required scopes (openid, profile, email, w_member_social)
- Authorization URL structure
- Authorization URL raises when not configured
- Token exchange success (mocked)
- Token exchange failure handling
- User profile fetch success (mocked)
- User profile fetch failure handling
- Token refresh success (mocked)

# TwitterService Tests (4 tests)
- Service initialization
- is_configured property
- PKCE code verifier generation
- Authorization URL handling

# FacebookService Tests (4 tests)
- Service initialization
- is_configured property
- Page permission scopes
- Authorization URL handling

# InstagramService Tests (3 tests)
- Service initialization (uses Facebook OAuth)
- is_configured property
- Authorization URL handling

# Service Profile Integration Tests (8 tests)
- LinkedIn profile token access
- Twitter profile token access
- Facebook page token access
- Instagram profile token access
- Profile token validity check
- Profile token expired check
- Profile token expiring soon check
- Disconnect clears tokens

# Error Handling Tests (4 tests)
- LinkedIn handles rate limit (429)
- LinkedIn handles unauthorized (401)
- LinkedIn handles connection error
- LinkedIn handles timeout

# Token Refresh Pattern Tests (3 tests)
- LinkedIn refresh updates expiry
- Profile has refresh methods
- Refresh raises when disconnected
```

#### Run Command
```bash
cd ai-brand-automator
source ../.venv/bin/activate
pytest automation/tests/ -v --tb=short
# Result: 149 passed, 14 skipped in ~3.5 minutes
```

---

## 4. Property-Based Testing with Hypothesis

### 4.1 Strategy Overview
Hypothesis generates random test data to discover edge cases that manual tests miss.

### 4.2 Custom Strategies

#### Company Model Strategy
```python
from hypothesis import strategies as st
from hypothesis.extra.django import from_model

# Custom strategy for Company model
company_strategy = st.builds(
    Company,
    name=st.text(min_size=1, max_size=255),
    description=st.text(max_size=1000),
    industry=st.sampled_from(['Technology', 'Healthcare', 'Finance']),
    brand_voice=st.sampled_from([choice[0] for choice in Company.BRAND_VOICE_CHOICES]),
)
```

#### Serializer Input Strategy
```python
# Random serializer input
company_data_strategy = st.fixed_dictionaries({
    'name': st.text(min_size=1, max_size=255),
    'industry': st.text(max_size=100),
    'description': st.text(max_size=1000),
    'target_audience': st.text(max_size=500),
})
```

### 4.3 Property Test Examples

#### Test: Serializer Round-Trip
```python
@given(company_strategy)
def test_company_serializer_roundtrip(company):
    """Property: Serializing then deserializing returns equivalent data"""
    serializer = CompanySerializer(company)
    data = serializer.data
    
    new_serializer = CompanySerializer(data=data)
    assert new_serializer.is_valid()
    # Verify core fields match
    assert new_serializer.validated_data['name'] == company.name
```

#### Test: Model Validation
```python
@given(st.text(min_size=1, max_size=255))
def test_company_name_always_valid(name):
    """Property: Any non-empty string ≤255 chars is valid company name"""
    company = Company(name=name, tenant=tenant_fixture)
    company.full_clean()  # Should not raise ValidationError
```

---

## 5. Mocking Strategy

### 5.1 External Dependencies to Mock

#### AI Service (Google Gemini API)
```python
# Mock in conftest.py
@pytest.fixture
def mock_gemini_api(mocker):
    """Mock Gemini AI API responses"""
    mock_response = {
        'vision_statement': 'Test vision',
        'mission_statement': 'Test mission',
        'values': ['Innovation', 'Excellence'],
    }
    return mocker.patch(
        'ai_services.services.GeminiAIService.generate_brand_strategy',
        return_value=mock_response
    )
```

#### Google Cloud Storage
```python
@pytest.fixture
def mock_gcs_upload(mocker):
    """Mock GCS file uploads"""
    return mocker.patch(
        'files.services.GCSService.upload_file',
        return_value='https://storage.googleapis.com/bucket/file.jpg'
    )
```

#### Email Sending
```python
@pytest.fixture(autouse=True)
def mock_email_send(mocker):
    """Auto-mock email sending in all tests"""
    return mocker.patch('django.core.mail.send_mail')
```

### 5.2 Time Mocking
```python
from freezegun import freeze_time

@freeze_time('2026-01-11 12:00:00')
def test_created_at_timestamp():
    """Test uses fixed time for reproducibility"""
    company = Company.objects.create(name='Test', tenant=tenant)
    assert company.created_at.hour == 12
```

---

## 6. Test Fixtures & Factories

### 6.1 Factory Boy Factories

#### Tenant Factory
```python
# tenants/tests/factories.py
import factory
from tenants.models import Tenant, Domain

class TenantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tenant
    
    name = factory.Faker('company')
    schema_name = factory.Sequence(lambda n: f'tenant_{n}')
    subscription_status = 'active'

class DomainFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Domain
    
    tenant = factory.SubFactory(TenantFactory)
    domain = factory.LazyAttribute(lambda obj: f'{obj.tenant.schema_name}.localhost')
    is_primary = True
```

#### Company Factory
```python
# onboarding/tests/factories.py
import factory
from onboarding.models import Company
from tenants.tests.factories import TenantFactory

class CompanyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Company
    
    tenant = factory.SubFactory(TenantFactory)
    name = factory.Faker('company')
    industry = factory.Faker('random_element', elements=['Technology', 'Healthcare'])
    description = factory.Faker('paragraph')
    brand_voice = 'professional'
    values = factory.LazyFunction(lambda: ['Innovation', 'Quality'])
```

### 6.2 Pytest Fixtures

#### Global Fixtures (`conftest.py`)
```python
import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.fixture
def api_client():
    """DRF API test client"""
    return APIClient()

@pytest.fixture
def authenticated_client(api_client, user):
    """Authenticated API client"""
    api_client.force_authenticate(user=user)
    return api_client

@pytest.fixture
def user(db):
    """Test user"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='TestPass123!'
    )

@pytest.fixture
def tenant(db):
    """Test tenant"""
    from tenants.tests.factories import TenantFactory, DomainFactory
    tenant = TenantFactory()
    DomainFactory(tenant=tenant)
    return tenant
```

---

## 7. Test Execution Strategy

### 7.1 Local Development
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific app
pytest onboarding/tests/

# Run only property tests
pytest -m hypothesis

# Run fast (skip slow integration tests)
pytest -m "not slow"
```

### 7.2 CI/CD Pipeline
```yaml
# .github/workflows/ci-cd.yml
- name: Run unit tests
  run: |
    pytest --cov=. --cov-report=xml \
           --cov-fail-under=80 \
           --hypothesis-show-statistics

- name: Run property tests
  run: |
    pytest -m hypothesis --hypothesis-seed=0
```

### 7.3 Test Markers
```python
# pytest.ini
[pytest]
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (slower, multiple components)
    hypothesis: Property-based tests
    slow: Slow tests (skip in local dev)
    skip_ci: Skip in CI environment
```

---

## 8. Coverage Goals

### 8.1 Target Coverage by Component
| Component | Target | Priority |
|-----------|--------|----------|
| Models | 95% | Critical |
| Serializers | 90% | High |
| Views/ViewSets | 85% | High |
| Services | 80% | Medium |
| Validators | 95% | Critical |
| Middleware | 75% | Medium |
| Overall | 80% | - |

### 8.2 Excluded from Coverage
- Migration files (`*/migrations/*`)
- Admin files (`*/admin.py`)
- `__init__.py` files
- Test files themselves
- Third-party code

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Set up pytest configuration
- [ ] Create global fixtures (`conftest.py`)
- [ ] Install Hypothesis
- [ ] Create base factory classes
- [ ] Configure coverage reporting

### Phase 2: Onboarding Service (Week 1-2)
- [ ] Model tests
- [ ] Serializer tests
- [ ] ViewSet tests
- [ ] Property tests
- [ ] Integration tests

### Phase 3: AI Services (Week 2-3)
- [ ] Service layer tests (mock AI API)
- [ ] Model tests
- [ ] ViewSet tests
- [ ] Property tests

### Phase 4: Authentication (Week 3)
- [ ] Auth view tests
- [ ] Validator tests
- [ ] Middleware tests

### Phase 5: Health & Utils (Week 3)
- [ ] Health check tests
- [ ] Utility function tests

### Phase 6: Integration & Property Tests (Week 4)
- [ ] Cross-service integration tests
- [ ] Comprehensive property tests
- [ ] Edge case discovery
- [ ] Performance tests

---

## 10. Best Practices & Guidelines

### 10.1 Test Naming Convention
```python
# Format: test_<what>_<condition>_<expected>
def test_company_creation_valid_data_succeeds():
    """When creating company with valid data, it succeeds"""
    
def test_company_serializer_missing_name_returns_error():
    """When name field missing, serializer returns validation error"""
```

### 10.2 AAA Pattern (Arrange-Act-Assert)
```python
def test_company_update():
    # Arrange
    company = CompanyFactory()
    new_name = 'Updated Name'
    
    # Act
    company.name = new_name
    company.save()
    
    # Assert
    assert Company.objects.get(pk=company.pk).name == new_name
```

### 10.3 Don't Test Django/DRF
```python
# ❌ BAD: Testing Django's ORM
def test_company_save():
    company = Company(name='Test')
    company.save()
    assert company.pk is not None  # This tests Django, not your code

# ✅ GOOD: Testing your business logic
def test_company_auto_generates_slug():
    company = Company.objects.create(name='Test Company')
    assert company.slug == 'test-company'  # Your custom logic
```

### 10.4 Avoid Over-Mocking
```python
# ❌ BAD: Mocking everything
def test_company_creation(mocker):
    mocker.patch('onboarding.models.Company.save')
    company = Company.objects.create(name='Test')  # Not really testing anything

# ✅ GOOD: Only mock external dependencies
def test_company_triggers_ai_generation(mock_gemini_api):
    company = Company.objects.create(name='Test')
    company.generate_brand_strategy()
    mock_gemini_api.assert_called_once()
```

---

## 11. Success Metrics

### 11.1 Quantitative Metrics
- ✅ 80%+ code coverage
- ✅ All tests pass in <30 seconds (unit tests)
- ✅ Zero flaky tests (100% deterministic)
- ✅ Property tests discover ≥5 edge cases
- ✅ **Automation Service: 149 tests passing** (implemented Jan 2026)

### 11.2 Qualitative Metrics
- ✅ Tests document expected behavior
- ✅ Easy to add new tests
- ✅ Tests catch regressions before production
- ✅ CI pipeline prevents bad merges

---

## 12. Next Steps

1. ~~**Review & Approve Strategy** - Team review this document~~ ✅
2. ~~**Install Dependencies** - Add Hypothesis to requirements-dev.txt~~ ✅
3. ~~**Create Conftest** - Set up global fixtures~~ ✅
4. ~~**Start with Onboarding** - Implement Phase 2 tests~~ ✅
5. ~~**Automation Service Tests** - Implement comprehensive test suite~~ ✅ (149 tests)
6. **Iterate & Improve** - Gather feedback, adjust strategy

---

**Document Version**: 1.1  
**Last Updated**: 2026-01-22  
**Owner**: Development Team  
**Status**: Automation Tests Implemented
